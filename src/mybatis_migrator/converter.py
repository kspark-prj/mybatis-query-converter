import csv
import html
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from sqlglot import exp, parse_one
from sqlglot.expressions.core import Expression


@dataclass
class ReviewItem:
    file_path: str
    query_id: str
    reason: str
    status: str  # "AST_FAIL", "WARNING", "FALLBACK_APPLIED"
    original_query: str = ""
    converted_query: str = ""


@dataclass
class SuccessItem:
    file_path: str
    query_id: str


class MyBatisASTConverter:
    SUPPORTED_DIALECTS: ClassVar[list[str]] = [
        "oracle",
        "postgres",
        "mysql",
        "mssql",
        "sqlite",
        "mariadb",
        "duckdb",
        "snowflake",
        "redshift",
        "clickhouse",
        "bigquery",
        "trino",
        "db2",
    ]

    DIALECT_ALIAS_MAP: ClassVar[dict[str, str]] = {
        "mssql": "tsql",
        "sqlserver": "tsql",
        "postgresql": "postgres",
        "mariadb": "mysql",
    }

    def __init__(
        self,
        source_db: str = "oracle",
        target_db: str = "postgres",
        log_file: str | None = "migration_review.csv",
    ):
        self.source_db = source_db.lower()
        self.target_db = target_db.lower()
        self.log_file = log_file
        self.review_items: list[ReviewItem] = []
        self.success_items: list[SuccessItem] = []
        self.total_queries_count: int = 0

    @classmethod
    def normalize_dialect(cls, name: str) -> str:
        clean_name = name.strip().lower()
        return cls.DIALECT_ALIAS_MAP.get(clean_name, clean_name)

    def clear_reviews(self):
        self.review_items.clear()
        self.success_items.clear()
        self.total_queries_count = 0

    def log_review_target(
        self,
        file_path: str,
        query_id: str,
        reason: str,
        status: str = "WARNING",
        orig_query: str = "",
        conv_query: str = "",
    ) -> ReviewItem:
        item = ReviewItem(
            file_path=str(file_path),
            query_id=query_id,
            reason=reason,
            status=status,
            original_query=orig_query,
            converted_query=conv_query,
        )
        self.review_items.append(item)
        return item

    # [추가 보완 5] Oracle 날짜 포맷 스트링 변환 지원 (TO_CHAR / TO_DATE)
    def _convert_oracle_date_format(self, text: str) -> str:
        s_db = self.normalize_dialect(self.source_db)
        t_db = self.normalize_dialect(self.target_db)

        if s_db == "oracle" and t_db == "mysql":

            def oracle_fmt_to_mysql(m):
                col = m.group(1)
                fmt = m.group(2)
                fmt_conv = (
                    fmt.replace("YYYY", "%Y")
                    .replace("MM", "%m")
                    .replace("DD", "%d")
                    .replace("HH24", "%H")
                    .replace("MI", "%i")
                    .replace("SS", "%s")
                )
                return f"DATE_FORMAT({col}, '{fmt_conv}')"

            text = re.sub(
                r"\bTO_CHAR\(([^,]+),\s*['\"]([^'\"]+)['\"]\)",
                oracle_fmt_to_mysql,
                text,
                flags=re.IGNORECASE,
            )
        return text

    def fallback_regex_transform(self, text: str) -> str:
        transformed = text
        s_db = self.normalize_dialect(self.source_db)
        t_db = self.normalize_dialect(self.target_db)

        # [추가 보완 5] 날짜 포맷 변환 수행
        transformed = self._convert_oracle_date_format(transformed)

        if s_db == "tsql" and t_db != "tsql":
            transformed = re.sub(r"WITH\s*\(\s*NOLOCK\s*\)", "", transformed, flags=re.IGNORECASE)
            transformed = re.sub(r"\(\s*NOLOCK\s*\)", "", transformed, flags=re.IGNORECASE)

        if s_db == "oracle":
            # [추가 보완 3] Oracle (+) 단순 제거
            transformed = re.sub(
                r"([a-zA-Z0-9_\.]+)\s*\(\s*\+\s*\)", r"\1", transformed, flags=re.IGNORECASE
            )
            if t_db in ("postgres", "sqlite", "duckdb"):
                transformed = re.sub(
                    r"\bNVL2\(([^,]+),\s*([^,]+),\s*([^)]+)\)",
                    r"CASE WHEN \1 IS NOT NULL THEN \2 ELSE \3 END",
                    transformed,
                    flags=re.IGNORECASE,
                )
                transformed = re.sub(r"\bNVL\b", "COALESCE", transformed, flags=re.IGNORECASE)
                transformed = re.sub(
                    r"\bSYSDATE\b", "CURRENT_TIMESTAMP", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"\bSYSTIMESTAMP\b", "CURRENT_TIMESTAMP", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"(\w+)\.NEXTVAL\b", r"nextval('\1')", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"(\w+)\.CURRVAL\b", r"currval('\1')", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"WHERE\s+ROWNUM\s*<=\s*(\d+)", r"LIMIT \1", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"AND\s+ROWNUM\s*<=\s*(\d+)", r"LIMIT \1", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"WHERE\s+ROWNUM\s*=\s*1\b", r"LIMIT 1", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"AND\s+ROWNUM\s*=\s*1\b", r"LIMIT 1", transformed, flags=re.IGNORECASE
                )
            elif t_db == "mysql":
                transformed = re.sub(
                    r"\bNVL2\(([^,]+),\s*([^,]+),\s*([^)]+)\)",
                    r"CASE WHEN \1 IS NOT NULL THEN \2 ELSE \3 END",
                    transformed,
                    flags=re.IGNORECASE,
                )
                transformed = re.sub(r"\bNVL\b", "IFNULL", transformed, flags=re.IGNORECASE)
                transformed = re.sub(r"\bSYSDATE\b", "NOW()", transformed, flags=re.IGNORECASE)
                transformed = re.sub(r"\bSYSTIMESTAMP\b", "NOW()", transformed, flags=re.IGNORECASE)
                transformed = re.sub(
                    r"WHERE\s+ROWNUM\s*<=\s*(\d+)", r"LIMIT \1", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"AND\s+ROWNUM\s*<=\s*(\d+)", r"LIMIT \1", transformed, flags=re.IGNORECASE
                )
            elif t_db == "tsql":
                transformed = re.sub(
                    r"\bNVL2\(([^,]+),\s*([^,]+),\s*([^)]+)\)",
                    r"CASE WHEN \1 IS NOT NULL THEN \2 ELSE \3 END",
                    transformed,
                    flags=re.IGNORECASE,
                )
                transformed = re.sub(r"\bNVL\b", "ISNULL", transformed, flags=re.IGNORECASE)
                transformed = re.sub(r"\bSYSDATE\b", "GETDATE()", transformed, flags=re.IGNORECASE)
                transformed = re.sub(
                    r"(\w+)\.NEXTVAL\b", r"NEXT VALUE FOR \1", transformed, flags=re.IGNORECASE
                )
        elif s_db == "mysql":
            if t_db == "postgres":
                transformed = re.sub(r"\bIFNULL\b", "COALESCE", transformed, flags=re.IGNORECASE)
                transformed = re.sub(
                    r"\bNOW\(\)", "CURRENT_TIMESTAMP", transformed, flags=re.IGNORECASE
                )
                # MySQL ON DUPLICATE KEY UPDATE → PostgreSQL ON CONFLICT (...) DO UPDATE SET
                # 1) INSERT 대상 컬럼 목록에서 첫 번째 컬럼(PK 후보) 추출
                insert_col_match = re.search(
                    r"\bINSERT\s+INTO\s+[a-zA-Z0-9_\.`\"\[\]]+\s*\(([^)]+)\)",
                    transformed,
                    flags=re.IGNORECASE,
                )
                if insert_col_match:
                    raw_col = insert_col_match.group(1).split(",")[0].strip()
                    clean_col = re.sub(r"[`\"'\[\]\s]", "", raw_col)
                    conflict_target = f"({clean_col})" if clean_col else "(/* TODO: specify PK column */)"
                else:
                    conflict_target = "(/* TODO: specify PK column */)"

                # sqlglot이 Postgres 출력 시 SET을 추가할 수 있으므로 optional SET 포함 (중복 SET 방지)
                transformed = re.sub(
                    r"\bON\s+DUPLICATE\s+KEY\s+UPDATE\b(?:\s+SET)?",
                    f"ON CONFLICT {conflict_target} DO UPDATE SET",
                    transformed,
                    flags=re.IGNORECASE,
                )

                # 2) MySQL VALUES(col) → PostgreSQL EXCLUDED.col 변환 (테이블명/따옴표 제거 처리)
                def _mysql_values_to_postgres_excluded(m):
                    expr = m.group(1).strip()
                    if "." in expr:
                        expr = expr.split(".")[-1]
                    clean_expr = re.sub(r"[`\"'\[\]]", "", expr)
                    return f"EXCLUDED.{clean_expr}"

                transformed = re.sub(
                    r"\bVALUES\s*\(\s*([a-zA-Z0-9_\.`\"\[\]]+)\s*\)",
                    _mysql_values_to_postgres_excluded,
                    transformed,
                    flags=re.IGNORECASE,
                )
            elif t_db == "oracle":
                transformed = re.sub(r"\bIFNULL\b", "NVL", transformed, flags=re.IGNORECASE)
                transformed = re.sub(r"\bNOW\(\)", "SYSDATE", transformed, flags=re.IGNORECASE)
                transformed = re.sub(
                    r"LIMIT\s+(\d+)", r"FETCH FIRST \1 ROWS ONLY", transformed, flags=re.IGNORECASE
                )
        elif s_db == "tsql":
            if t_db == "postgres":
                transformed = re.sub(r"\bISNULL\b", "COALESCE", transformed, flags=re.IGNORECASE)
                transformed = re.sub(
                    r"\bGETDATE\(\)", "CURRENT_TIMESTAMP", transformed, flags=re.IGNORECASE
                )
            elif t_db == "oracle":
                transformed = re.sub(r"\bISNULL\b", "NVL", transformed, flags=re.IGNORECASE)
                transformed = re.sub(r"\bGETDATE\(\)", "SYSDATE", transformed, flags=re.IGNORECASE)
            elif t_db == "mysql":
                transformed = re.sub(r"\bISNULL\b", "IFNULL", transformed, flags=re.IGNORECASE)
                transformed = re.sub(r"\bGETDATE\(\)", "NOW()", transformed, flags=re.IGNORECASE)
        elif s_db == "postgres":
            if t_db == "oracle":
                transformed = re.sub(r"\bCOALESCE\b", "NVL", transformed, flags=re.IGNORECASE)
                transformed = re.sub(
                    r"\bCURRENT_TIMESTAMP\b", "SYSDATE", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"LIMIT\s+(\d+)", r"FETCH FIRST \1 ROWS ONLY", transformed, flags=re.IGNORECASE
                )
            elif t_db == "mysql":
                transformed = re.sub(
                    r"\bCURRENT_TIMESTAMP\b", "NOW()", transformed, flags=re.IGNORECASE
                )
                transformed = re.sub(
                    r"\bSTRING_AGG\(([^,]+),\s*([^)]+)\)",
                    r"GROUP_CONCAT(\1 SEPARATOR \2)",
                    transformed,
                    flags=re.IGNORECASE,
                )
                transformed = re.sub(
                    r"\bSTRPOS\(([^,]+),\s*([^)]+)\)",
                    r"LOCATE(\2, \1)",
                    transformed,
                    flags=re.IGNORECASE,
                )
                transformed = re.sub(
                    r"\bRETURNING\s+[a-zA-Z0-9_,\s\*\.]+", "", transformed, flags=re.IGNORECASE
                )
                # sqlglot이 MySQL 출력 시 DO UPDATE (SET 없이) 출력할 수 있으므로 optional SET
                transformed = re.sub(
                    r"\bON\s+CONFLICT\b[\s\S]*?\bDO\s+UPDATE\b(?:\s+SET)?",
                    "ON DUPLICATE KEY UPDATE",
                    transformed,
                    flags=re.IGNORECASE,
                )
                # PostgreSQL EXCLUDED.col → MySQL VALUES(col) 변환 (식별자 따옴표 제거)
                def _postgres_excluded_to_mysql_values(m):
                    clean_col = re.sub(r"[`\"'\[\]]", "", m.group(1))
                    return f"VALUES({clean_col})"

                transformed = re.sub(
                    r"\bEXCLUDED\.([a-zA-Z0-9_`\"\[\]]+)\b",
                    _postgres_excluded_to_mysql_values,
                    transformed,
                    flags=re.IGNORECASE,
                )

        return transformed

    def transform_connect_by_to_cte(self, query_content: str) -> str:
        s_db = self.normalize_dialect(self.source_db)
        t_db = self.normalize_dialect(self.target_db)

        if s_db != "oracle" or t_db == "oracle":
            return query_content

        upper_query = query_content.upper()
        if "CONNECT BY" not in upper_query or "START WITH" not in upper_query:
            return query_content

        if upper_query.count("CONNECT BY") > 1 or upper_query.count("START WITH") > 1:
            return query_content

        cdata_present = False

        def unescape_cdata(m):
            nonlocal cdata_present
            cdata_present = True
            return html.unescape(m.group(1))

        raw_text = query_content
        sql_body = re.sub(
            r"<!\[CDATA\[([\s\S]*?)\]\]>", unescape_cdata, raw_text, flags=re.IGNORECASE
        )

        start_match = re.search(
            r"START\s+WITH\s+([\s\S]+?)(?=CONNECT\s+BY|ORDER\s+SIBLINGS|GROUP|HAVING|\)|$)",
            sql_body,
            re.IGNORECASE,
        )
        connect_match = re.search(
            r"CONNECT\s+BY\s+([\s\S]+?)(?=ORDER\s+SIBLINGS|GROUP|HAVING|\)|$)",
            sql_body,
            re.IGNORECASE,
        )

        if not start_match or not connect_match:
            return query_content

        start_cond = start_match.group(1).strip()
        connect_clause = connect_match.group(1).strip()

        prior_match = re.search(
            r"(?:PRIOR\s+([a-zA-Z0-9_\.]+)\s*=\s*([a-zA-Z0-9_\.]+))|(?:([a-zA-Z0-9_\.]+)\s*=\s*PRIOR\s+([a-zA-Z0-9_\.]+))",
            connect_clause,
            re.IGNORECASE,
        )

        if not prior_match:
            return query_content

        if prior_match.group(1):
            parent_col = prior_match.group(1)
            child_col = prior_match.group(2)
        else:
            child_col = prior_match.group(3)
            parent_col = prior_match.group(4)

        from_match = re.search(r"FROM\s+([a-zA-Z0-9_\.]+)", sql_body, re.IGNORECASE)
        if not from_match:
            return query_content

        table_name = from_match.group(1)

        select_match = re.search(r"SELECT\s+([\s\S]+?)\s+FROM\b", sql_body, re.IGNORECASE)
        if not select_match:
            return query_content
        select_cols = select_match.group(1).strip()

        where_match = re.search(
            r"WHERE\s+([\s\S]+?)(?=START\s+WITH|CONNECT\s+BY|ORDER|GROUP|$)",
            sql_body,
            re.IGNORECASE,
        )
        where_cond = ""
        rownum_limit = None

        if where_match:
            raw_where = where_match.group(1).strip()
            rownum_match = re.search(r"(?:ROWNUM|li|rn|row_num|level)\s*<=?\s*(\d+)", raw_where, re.IGNORECASE)
            if rownum_match:
                rownum_limit = rownum_match.group(1)

            clean_where = re.sub(
                r"(?:AND|WHERE)?\s*(?:ROWNUM|li|rn|row_num|level)\s*<=?\s*\d+", "", raw_where, flags=re.IGNORECASE
            ).strip()
            for _ in range(3):
                clean_where = re.sub(r"^(?:AND|OR)\s+", "", clean_where, flags=re.IGNORECASE).strip()
                clean_where = re.sub(r"\s+(?:AND|OR)$", "", clean_where, flags=re.IGNORECASE).strip()
                clean_where = re.sub(r"\b(?:AND|OR)\s+(?:AND|OR)\b", "AND", clean_where, flags=re.IGNORECASE).strip()
            if clean_where:
                where_cond = clean_where

        anchor_where = f"WHERE ({start_cond})"
        if where_cond:
            anchor_where += f" AND ({where_cond})"

        recursive_where = f"ON T.{parent_col} = E.{child_col}"
        if where_cond:
            recursive_where += f"\n  WHERE E.{where_cond}"

        cte_name = "CTE_HIERARCHY"

        cte_sql = f"""WITH RECURSIVE {cte_name} AS (
  SELECT *, 1 AS LEVEL
  FROM {table_name}
  {anchor_where}

  UNION ALL

  SELECT E.*, T.LEVEL + 1 AS LEVEL
  FROM {table_name} E
  JOIN {cte_name} T {recursive_where}
)
SELECT {select_cols}
FROM {cte_name}"""

        order_match = re.search(r"ORDER\s+SIBLINGS\s+BY\s+([\s\S]+?)$", sql_body, re.IGNORECASE)
        if order_match:
            order_col = order_match.group(1).strip()
            cte_sql += f"\nORDER BY {order_col}"

        if rownum_limit:
            cte_sql += f"\nLIMIT {rownum_limit}"

        return cte_sql

    def transform_ast(self, expression: Expression) -> Expression:
        if not expression:
            return expression

        s_db = self.normalize_dialect(self.source_db)
        t_db = self.normalize_dialect(self.target_db)

        # [추가 보완 4] PostgreSQL Target: 서브쿼리(Derived Table) 필수 Alias 자동 추가
        if t_db == "postgres":
            for subq in expression.find_all(exp.Subquery):
                if not subq.alias and isinstance(subq.parent, (exp.From, exp.Join)):
                    subq.set("alias", exp.TableAlias(this=exp.to_identifier("subq_auto")))

        # Oracle -> 타 DB 변환
        if s_db == "oracle":
            where_clause = expression.args.get("where")
            if where_clause:
                limit_val = None

                def extract_rownum_from_node(node):
                    if isinstance(node, (exp.LTE, exp.LT, exp.EQ)):
                        if isinstance(node.this, exp.Column) and node.this.name.upper() == "ROWNUM":
                            if isinstance(node.expression, exp.Literal):
                                return int(node.expression.this)
                        elif (
                            isinstance(node.expression, exp.Column)
                            and node.expression.name.upper() == "ROWNUM"
                            and isinstance(node.this, exp.Literal)
                        ):
                            return int(node.this.this)
                    return None

                for node in list(where_clause.find_all(exp.LTE, exp.LT, exp.EQ)):
                    l_v = extract_rownum_from_node(node)
                    if l_v is not None:
                        limit_val = l_v
                        parent = node.parent
                        if parent == where_clause:
                            expression.set("where", None)
                        elif isinstance(parent, exp.And):
                            other = parent.expression if parent.this == node else parent.this
                            parent.replace(other)
                        else:
                            node.replace(exp.true())
                        break

                if limit_val is not None and isinstance(expression, exp.Select):
                    if t_db in ("postgres", "mysql", "sqlite", "duckdb"):
                        expression.set("limit", exp.Limit(expression=exp.Literal.number(limit_val)))
                    elif t_db == "oracle":
                        expression.set(
                            "limit",
                            exp.Fetch(direction="FIRST", count=exp.Literal.number(limit_val)),
                        )

            for col in expression.find_all(exp.Column):
                if col.name.upper() == "NEXTVAL" and col.table:
                    seq_name = col.table
                    if t_db == "postgres":
                        func = exp.Anonymous(
                            this="nextval", expressions=[exp.Literal.string(seq_name)]
                        )
                        col.replace(func)
                    elif t_db in ("tsql", "mssql"):
                        func = exp.Anonymous(
                            this="NEXT VALUE FOR",
                            expressions=[exp.Column(this=exp.Identifier(this=seq_name))],
                        )
                        col.replace(func)
                elif col.name.upper() == "CURRVAL" and col.table:
                    seq_name = col.table
                    if t_db == "postgres":
                        func = exp.Anonymous(
                            this="currval", expressions=[exp.Literal.string(seq_name)]
                        )
                        col.replace(func)

            if t_db == "postgres" and isinstance(expression, exp.Select):
                from_clause = expression.args.get("from") or expression.args.get("from_")
                if (
                    from_clause
                    and isinstance(from_clause.this, exp.Table)
                    and from_clause.this.name.upper() == "DUAL"
                ):
                    expression.args.pop("from", None)
                    expression.args.pop("from_", None)

        return expression

    def transform_single_query(
        self, query_content: str, query_id: str = "MANUAL", file_path: str = "MANUAL"
    ) -> str:
        self.total_queries_count += 1
        raw_original_query = query_content

        cdata_present = False
        if re.search(r"<!\[CDATA\[", query_content, re.IGNORECASE):
            cdata_present = True

        def unwrap_cdata(m):
            return html.unescape(m.group(1))

        query_content = re.sub(
            r"<!\[CDATA\[([\s\S]*?)\]\]>", unwrap_cdata, query_content, flags=re.IGNORECASE
        )
        query_content = html.unescape(query_content)

        query_content = self.transform_connect_by_to_cte(query_content)

        token_map = {}
        counter = 0

        def get_token(prefix):
            nonlocal counter
            counter += 1
            return f"__MBTOK_{prefix}_{counter}__"

        masked_text = query_content

        def mask_param(m):
            tok = get_token("PRM")
            token_map[tok] = m.group(0)
            return tok

        masked_text = re.sub(r"[#\$]\{[^}]+\}", mask_param, masked_text)

        # [추가 보완 2] <foreach> 사용 문맥(IN vs VALUES) 파악 후 Dummy 값 다변화 마스킹
        def mask_foreach(m):
            tok = get_token("FOREACH")
            token_map[tok] = m.group(0)
            start_pos = m.start()
            prefix_text = masked_text[max(0, start_pos - 40) : start_pos].upper()

            if "IN" in prefix_text or "VALUES" in prefix_text:
                return f"('{tok}_VAL1', '{tok}_VAL2')"
            return f"'{tok}'"

        masked_text = re.sub(
            r"<foreach[\s\S]*?</foreach>", mask_foreach, masked_text, flags=re.IGNORECASE
        )

        def mask_tag(m):
            tag_str = m.group(0)
            is_close = tag_str.startswith("</")
            match_name = re.match(r"</?([a-zA-Z0-9_\-]+)", tag_str)
            tag_name = match_name.group(1).lower() if match_name else ""

            if is_close:
                tok = get_token(f"CLOSE_{tag_name.upper()}")
                token_map[tok] = tag_str
                return f" /* {tok} */ "
            else:
                tok = get_token(f"OPEN_{tag_name.upper()}")
                token_map[tok] = tag_str

                if tag_name == "set":
                    return f" SET __MB_DUMMY_SET__ = 1 /* {tok} */ , "
                elif tag_name == "where":
                    return f" WHERE 1=1 /* {tok} */ AND "
                elif tag_name == "trim":
                    prefix_match = re.search(r'prefix=["\']([^"\']+)["\']', tag_str, re.IGNORECASE)
                    prefix_val = prefix_match.group(1).upper() if prefix_match else ""
                    if prefix_val == "WHERE":
                        return f" WHERE 1=1 /* {tok} */ AND "
                    elif prefix_val == "SET":
                        return f" SET __MB_DUMMY_SET__ = 1 /* {tok} */ , "
                    elif prefix_val:
                        return f" {prefix_val} /* {tok} */ "
                    return f" /* {tok} */ "
                else:
                    return f" /* {tok} */ "

        masked_text = re.sub(r"</?[a-zA-Z0-9_\-]+[^>]*>", mask_tag, masked_text)

        masked_text = re.sub(
            r"(\bWHERE\s+1=1\s*(?:/\*.*?\*/\s*)*AND\s+(?:/\*.*?\*/\s*)*)\b(?:AND|OR)\b",
            r"\1",
            masked_text,
            flags=re.IGNORECASE,
        )

        def mask_trailing_comma(m):
            tok = get_token("TRM_COMMA")
            token_map[tok] = ","
            close_tags = m.group(1)
            if re.search(r"CLOSE_(SET|TRIM|WHERE)", close_tags, re.IGNORECASE):
                return f" /* {tok} */ {close_tags}"
            return m.group(0)

        masked_text = re.sub(
            r",\s*((?:/\*\s*__MBTOK_CLOSE_[^*]+\*/\s*)+)",
            mask_trailing_comma,
            masked_text,
            flags=re.IGNORECASE,
        )

        transformed_sql = ""
        ast_success = False

        read_dialect = self.normalize_dialect(self.source_db)
        write_dialect = self.normalize_dialect(self.target_db)

        try:
            expression = parse_one(masked_text, read=read_dialect)
            if expression:
                expression = self.transform_ast(expression)
                transformed_sql = expression.sql(dialect=write_dialect, pretty=True)
                ast_success = True
            else:
                raise ValueError("AST 파싱 결과가 비어있음")
        except Exception as e:  # noqa: BLE001
            err_msg = str(e)[:150]
            transformed_sql = self.fallback_regex_transform(query_content)

            # [추가 보완 3] Oracle (+) 구문 포함 시 Fallback 정밀 경고 로그 작성
            reason_str = f"AST 파싱 실패 (정규식 Fallback 적용): {err_msg}"
            if read_dialect == "oracle" and "(+)" in raw_original_query:
                reason_str += " | Oracle Outer Join 기호(+)가 단순 제거됨 (ANSI LEFT/RIGHT JOIN 수동 검수 필수)"

            if cdata_present:
                transformed_sql = f"<![CDATA[\n{transformed_sql.strip()}\n]]>"

            self.log_review_target(
                file_path=file_path,
                query_id=query_id,
                reason=reason_str,
                status="AST_FAIL",
                orig_query=raw_original_query,
                conv_query=transformed_sql,
            )
            return transformed_sql

        if ast_success:
            kw_pattern = r"(?!(?:SET|WHERE|SELECT|FROM|VALUES|INSERT|UPDATE|DELETE|INTO|AND|OR|BY|ORDER|GROUP|HAVING|LIMIT|OFFSET|JOIN|LEFT|RIGHT|INNER|OUTER)\b)\w+"

            transformed_sql = re.sub(
                rf"(\b{kw_pattern}\b)\s*(/\*\s*__MBTOK_CLOSE_(?:IF|WHEN)[^*]*\*/)",
                r"\2 \1",
                transformed_sql,
            )
            transformed_sql = re.sub(
                rf"(\b{kw_pattern}\b)\s*(/\*\s*__MBTOK_OPEN_(?:IF|WHEN)[^*]*\*/)",
                r"\2 \1",
                transformed_sql,
            )

            for tok, orig in reversed(list(token_map.items())):
                if orig.lower().startswith("<set") or 'prefix="set"' in orig.lower():
                    transformed_sql = re.sub(
                        r"SET\s+__MB_DUMMY_SET__\s*=\s*1\s*/\*\s*"
                        + re.escape(tok)
                        + r"\s*\*/(?:\s*,)?",
                        orig,
                        transformed_sql,
                        flags=re.IGNORECASE,
                    )
                    transformed_sql = re.sub(
                        r"/\*\s*" + re.escape(tok) + r"\s*\*/",
                        orig,
                        transformed_sql,
                        flags=re.IGNORECASE,
                    )
                    transformed_sql = re.sub(
                        r"__MB_DUMMY_SET__\s*=\s*1\s*,?",
                        "",
                        transformed_sql,
                        flags=re.IGNORECASE,
                    )
                elif orig.lower().startswith("<where") or 'prefix="where"' in orig.lower():
                    transformed_sql = re.sub(
                        r"WHERE\s+1\s*=\s*1\s*/\*\s*"
                        + re.escape(tok)
                        + r"\s*\*/(?:\s*(?:AND|OR))?",
                        orig,
                        transformed_sql,
                        flags=re.IGNORECASE,
                    )
                    transformed_sql = re.sub(
                        r"/\*\s*" + re.escape(tok) + r"\s*\*/",
                        orig,
                        transformed_sql,
                        flags=re.IGNORECASE,
                    )
                    transformed_sql = re.sub(
                        r"WHERE\s+1\s*=\s*1\s*(?:AND|OR)\b",
                        "",
                        transformed_sql,
                        flags=re.IGNORECASE,
                    )
                    transformed_sql = re.sub(
                        r"WHERE\s+1\s*=\s*1\b",
                        "",
                        transformed_sql,
                        flags=re.IGNORECASE,
                    )
                elif orig.lower().startswith("<trim"):
                    prefix_match = re.search(r'prefix=["\']([^"\']+)["\']', orig, re.IGNORECASE)
                    if prefix_match:
                        p_val = prefix_match.group(1).upper()
                        transformed_sql = re.sub(
                            re.escape(p_val)
                            + r"\s*1\s*=\s*1\s*/\*\s*"
                            + re.escape(tok)
                            + r"\s*\*/(?:\s*(?:AND|OR))?",
                            orig,
                            transformed_sql,
                            flags=re.IGNORECASE,
                        )
                        transformed_sql = re.sub(
                            re.escape(p_val) + r"\s*/\*\s*" + re.escape(tok) + r"\s*\*/",
                            orig,
                            transformed_sql,
                            flags=re.IGNORECASE,
                        )

                transformed_sql = transformed_sql.replace(f"/* {tok} */", orig)
                transformed_sql = transformed_sql.replace(f"/*{tok}*/", orig)
                transformed_sql = transformed_sql.replace(f"('{tok}_VAL1', '{tok}_VAL2')", orig)
                transformed_sql = transformed_sql.replace(f"'{tok}'", orig)
                transformed_sql = transformed_sql.replace(f'"{tok}"', orig)
                transformed_sql = transformed_sql.replace(f"`{tok}`", orig)
                transformed_sql = transformed_sql.replace(f"[{tok}]", orig)
                transformed_sql = transformed_sql.replace(tok, orig)

            transformed_sql = re.sub(
                r"\bWHERE\s+1\s*=\s*1\s*(?:AND|OR)\b", "WHERE", transformed_sql, flags=re.IGNORECASE
            )
            transformed_sql = re.sub(
                r"\bWHERE\s+1\s*=\s*1\b", "", transformed_sql, flags=re.IGNORECASE
            )
            transformed_sql = re.sub(
                r"__MB_DUMMY_SET__\s*=\s*1\s*,?", "", transformed_sql, flags=re.IGNORECASE
            )

            transformed_sql = self.fallback_regex_transform(transformed_sql)

            before_review = len(self.review_items)

            if read_dialect == "oracle" and (
                "CONNECT BY" in raw_original_query.upper()
                or "WITH RECURSIVE" in transformed_sql.upper()
            ):
                self.log_review_target(
                    file_path=file_path,
                    query_id=query_id,
                    reason="오라클 계층형 쿼리(CONNECT BY) -> CTE(WITH RECURSIVE) 자동 변환 완료 (수동 검수 권장)",
                    status="WARNING",
                    orig_query=raw_original_query,
                    conv_query=transformed_sql,
                )
            elif (
                read_dialect == "oracle"
                and "ROWNUM" in raw_original_query.upper()
                and "LIMIT" not in transformed_sql.upper()
                and "FETCH" not in transformed_sql.upper()
            ):
                self.log_review_target(
                    file_path=file_path,
                    query_id=query_id,
                    reason="ROWNUM 구문 변환 확인 필요",
                    status="WARNING",
                    orig_query=raw_original_query,
                    conv_query=transformed_sql,
                )
            elif "RETURNING" in raw_original_query.upper() and write_dialect in ("mysql", "sqlite", "oracle"):
                self.log_review_target(
                    file_path=file_path,
                    query_id=query_id,
                    reason=f"Target DB({write_dialect})는 RETURNING 구문을 지원하지 않습니다.",
                    status="WARNING",
                    orig_query=raw_original_query,
                    conv_query=transformed_sql,
                )

            if len(self.review_items) == before_review:
                self.success_items.append(SuccessItem(file_path=str(file_path), query_id=query_id))

        if cdata_present:
            transformed_sql = f"<![CDATA[\n{transformed_sql.strip()}\n]]>"

        return transformed_sql

    # [추가 보완 1] XML 내 <sql id="..."> 조각을 수집하여 <include refid="..."/> 확장 처리 (최대 5레벨 중첩 지원)
    def _expand_includes(self, xml_content: str) -> str:
        sql_fragments = {}
        fragment_pattern = re.compile(
            r'<sql\b[^>]*\bid=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</sql>',
            re.IGNORECASE,
        )
        for m in fragment_pattern.finditer(xml_content):
            sql_fragments[m.group(1)] = m.group(2)

        if not sql_fragments:
            return xml_content

        expanded = xml_content
        include_pattern = re.compile(
            r'<include\b[^>]*\brefid=["\']([^"\']+)["\'][^>]*>(?:[\s\S]*?</include>)?|'
            r'<include\b[^>]*\brefid=["\']([^"\']+)["\'][^>]*\s*/?>',
            re.IGNORECASE,
        )

        for _ in range(5):

            def replacer(m):
                ref_id = m.group(1) or m.group(2)
                return sql_fragments.get(ref_id, m.group(0))

            new_expanded = include_pattern.sub(replacer, expanded)
            if new_expanded == expanded:
                break
            expanded = new_expanded

        return expanded

    def transform_xml_content(self, content: str, file_path: str = "MANUAL") -> str:
        # [추가 보완 1] include 태그 사전 펼치기 수행
        content = self._expand_includes(content)

        sql_tag_pattern = re.compile(
            r'(<(select|insert|update|delete|sql)\b[^>]*\bid=["\']([^"\']+)["\'][^>]*>)([\s\S]*?)(</\2>)',
            re.IGNORECASE,
        )

        matches = list(sql_tag_pattern.finditer(content))
        if not matches:
            return self.transform_single_query(
                content, query_id="SINGLE_QUERY", file_path=file_path
            )

        def replace_query_block(match):
            open_tag = match.group(1)
            query_id = match.group(3)
            query_body = match.group(4)
            close_tag = match.group(5)

            transformed_body = self.transform_single_query(query_body, query_id, file_path)

            res = open_tag
            if not res.endswith("\n"):
                res += "\n"
            
            lines = transformed_body.split("\n")
            indented = "\n".join("    " + line if line.strip() else line for line in lines)
            res += indented

            if not res.endswith("\n"):
                res += "\n"
            res += close_tag
            return res

        return sql_tag_pattern.sub(replace_query_block, content)

    def write_full_report(self, log_file_path: str | None = None):
        target_log = log_file_path or self.log_file
        if not target_log:
            return
        try:
            with open(target_log, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Type",
                        "Status",
                        "FilePath",
                        "QueryID",
                        "Reason",
                        "OriginalQuery",
                        "ConvertedQuery",
                    ]
                )

                for item in self.success_items:
                    writer.writerow(
                        ["SUCCESS", "SUCCESS", item.file_path, item.query_id, "", "", ""]
                    )

                for rev in self.review_items:
                    writer.writerow(
                        [
                            "REVIEW",
                            rev.status,
                            rev.file_path,
                            rev.query_id,
                            rev.reason,
                            rev.original_query,
                            rev.converted_query,
                        ]
                    )
        except Exception as e:  # noqa: BLE001
            print(f"[경고] 변환 리포트 파일 쓰기 실패 ({target_log}): {e}")

    def process_file(self, file_path: Path, save_path: Path) -> bool:
        try:
            with open(file_path, "r", encoding="utf-8", newline="") as f:
                content = f.read()

            detected_newline = "\r\n" if "\r\n" in content else "\n"
            transformed_content = self.transform_xml_content(content, file_path=str(file_path))

            transformed_content = transformed_content.replace("\r\n", "\n").replace(
                "\n", detected_newline
            )

            os.makedirs(save_path.parent, exist_ok=True)

            with open(save_path, "w", encoding="utf-8", newline=detected_newline) as f:
                f.write(transformed_content)
            return True
        except Exception as e:  # noqa: BLE001
            self.log_review_target(
                file_path=str(file_path),
                query_id="FILE_ERROR",
                reason=f"파일 읽기/쓰기 오류: {e!s}",
                status="AST_FAIL",
            )
            return False

    def process_directory(
        self,
        input_dir: str,
        output_dir: str | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[ReviewItem]:
        in_path = Path(input_dir).resolve()
        out_path = (
            Path(output_dir).resolve()
            if output_dir
            else in_path.parent / f"{in_path.name}_converted"
        )

        xml_files = list(in_path.glob("**/*.xml"))
        total_files = len(xml_files)

        for idx, xml_file in enumerate(xml_files, start=1):
            relative_path = xml_file.relative_to(in_path)
            save_path = out_path / relative_path

            if progress_callback:
                progress_callback(idx, total_files, str(relative_path))

            self.process_file(xml_file, save_path)

        self.write_full_report()
        return self.review_items
