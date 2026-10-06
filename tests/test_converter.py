import unittest

from mybatis_migrator.converter import MyBatisASTConverter


class TestMyBatisASTConverter(unittest.TestCase):
    def setUp(self):
        self.converter = MyBatisASTConverter(source_db="oracle", target_db="postgres", log_file=None)

    def test_single_query_nvl_sysdate(self):
        sql = "SELECT NVL(comm, 0), SYSDATE FROM emp WHERE empno = #{empNo}"
        res = self.converter.transform_single_query(sql, query_id="Q1")
        self.assertIn("COALESCE", res.upper())
        self.assertIn("CURRENT_TIMESTAMP", res.upper())
        self.assertIn("#{empNo}", res)

    def test_xml_content_transformation(self):
        xml = (
            '<select id="selectEmp" resultType="map">\n'
            '    SELECT NVL(sal, 0) AS sal FROM emp WHERE empno = #{empNo} AND ROWNUM <= 5\n'
            '</select>'
        )
        res = self.converter.transform_xml_content(xml)
        self.assertIn('<select id="selectEmp"', res)
        self.assertIn("COALESCE", res.upper())
        self.assertIn("LIMIT 5", res.upper())

    def test_connect_by_review_item(self):
        sql = "SELECT empno FROM emp START WITH mgr IS NULL CONNECT BY PRIOR empno = mgr"
        self.converter.clear_reviews()
        _ = self.converter.transform_single_query(sql, query_id="Q_HIERARCHICAL")
        reviews = self.converter.review_items
        self.assertTrue(len(reviews) > 0)
        self.assertEqual(reviews[0].query_id, "Q_HIERARCHICAL")
        self.assertIn("CONNECT BY", reviews[0].reason)
        self.assertEqual(reviews[0].original_query, sql)
        self.assertIn("WITH RECURSIVE", reviews[0].converted_query.upper())

    def test_mysql_to_postgres_generic(self):
        conv = MyBatisASTConverter(source_db="mysql", target_db="postgres", log_file=None)
        sql = "SELECT IFNULL(comm, 0), NOW() FROM emp WHERE dept_id = #{deptId} LIMIT 10 OFFSET 5"
        res = conv.transform_single_query(sql, query_id="Q_MYSQL")
        self.assertIn("COALESCE", res.upper())
        self.assertIn("CURRENT_TIMESTAMP", res.upper())
        self.assertIn("LIMIT 10", res.upper())
        self.assertIn("OFFSET 5", res.upper())

    def test_postgres_to_mysql_generic(self):
        conv = MyBatisASTConverter(source_db="postgres", target_db="mysql", log_file=None)
        sql = "SELECT COALESCE(sal, 0), CURRENT_TIMESTAMP, STRING_AGG(ename, ',') FROM emp WHERE name ILIKE '%test%' LIMIT 10 OFFSET 5"
        res = conv.transform_single_query(sql, query_id="Q_PG2MYSQL")
        self.assertIn("NOW()", res.upper())
        self.assertIn("GROUP_CONCAT", res.upper())
        self.assertIn("LIMIT 10", res.upper())

    def test_postgres_to_mysql_returning_warning(self):
        conv = MyBatisASTConverter(source_db="postgres", target_db="mysql", log_file=None)
        sql = "INSERT INTO emp (ename) VALUES (#{eName}) RETURNING empno"
        _ = conv.transform_single_query(sql, query_id="Q_RETURNING")
        reviews = conv.review_items
        self.assertTrue(len(reviews) > 0)
        self.assertIn("RETURNING", reviews[0].reason)

    def test_mssql_to_postgres_generic(self):
        conv = MyBatisASTConverter(source_db="mssql", target_db="postgres", log_file=None)
        sql = "SELECT TOP 10 ISNULL(sal, 0), GETDATE() FROM emp WHERE empno = #{empNo}"
        res = conv.transform_single_query(sql, query_id="Q_MSSQL")
        self.assertIn("COALESCE", res.upper())
        self.assertIn("LIMIT 10", res.upper())

    def test_postgres_to_oracle_generic(self):
        conv = MyBatisASTConverter(source_db="postgres", target_db="oracle", log_file=None)
        sql = "SELECT COALESCE(sal, 0), CURRENT_TIMESTAMP FROM emp LIMIT 10"
        res = conv.transform_single_query(sql, query_id="Q_PG2ORA")
        self.assertTrue("NVL" in res.upper() or "COALESCE" in res.upper())
        self.assertTrue("FETCH" in res.upper() or "ROWNUM" in res.upper() or "LIMIT" in res.upper())

    def test_update_query_with_set_and_if_tags(self):
        sql = (
            "<update id=\"updateUser\">\n"
            "    UPDATE TB_USER\n"
            "    <set>\n"
            "        <if test=\"userName != null\">\n"
            "            USER_NAME = #{userName},\n"
            "        </if>\n"
            "        POINT = NVL(#{point}, 0),\n"
            "        MOD_DATE = SYSDATE\n"
            "    </set>\n"
            "    WHERE USER_ID = #{userId}\n"
            "</update>"
        )
        res = self.converter.transform_xml_content(sql)
        self.assertIn("<set>", res)
        self.assertIn("COALESCE(#{point}, 0)", res)
        self.assertIn("CURRENT_TIMESTAMP", res)
        self.assertIn("#{userId}", res)
        # Ensure AST_FAIL was not triggered
        self.assertEqual(len(self.converter.review_items), 0)

    def test_oracle_sequence_nextval(self):
        sql = "INSERT INTO emp (empno, ename) VALUES (SEQ_EMP.NEXTVAL, #{eName})"
        res = self.converter.transform_single_query(sql, query_id="Q_SEQ")
        self.assertIn("NEXTVAL('SEQ_EMP')", res.upper())

    def test_oracle_decode(self):
        sql = "SELECT DECODE(USE_YN, 'Y', '사용중', '미사용') AS STATUS FROM TB_DEPT"
        res = self.converter.transform_single_query(sql, query_id="Q_DECODE")
        self.assertIn("CASE WHEN USE_YN = 'Y' THEN '사용중' ELSE '미사용' END", res)

    def test_dual_table_removal(self):
        sql = "SELECT SYSDATE FROM DUAL"
        res = self.converter.transform_single_query(sql, query_id="Q_DUAL")
        self.assertIn("CURRENT_TIMESTAMP", res.upper())
        self.assertNotIn("DUAL", res.upper())

    def test_oracle_connect_by_auto_cte(self):
        sql = (
            "SELECT EMPNO, ENAME, NVL(COMM, 0) AS COMM, SYSDATE AS NOW_DATE\n"
            "FROM EMP\n"
            "WHERE DEPTNO = #{deptNo}\n"
            "  AND ROWNUM <= 10\n"
            "START WITH MGR_ID IS NULL\n"
            "CONNECT BY PRIOR EMPNO = MGR_ID"
        )
        res = self.converter.transform_single_query(sql, query_id="Q_CTE")
        self.assertIn("WITH RECURSIVE", res.upper())
        self.assertIn("CTE_HIERARCHY", res.upper())
        self.assertIn("COALESCE", res.upper())
        self.assertIn("CURRENT_TIMESTAMP", res.upper())
        self.assertIn("LIMIT 10", res.upper())

    def test_cdata_connect_by_tag_placement(self):
        xml = (
            '<select id="selectEmpList" parameterType="map" resultType="empVo">\n'
            '    <![CDATA[\n'
            '    SELECT EMPNO, ENAME, NVL(COMM, 0) AS COMM, SYSDATE AS NOW_DATE\n'
            '    FROM EMP\n'
            '    WHERE DEPTNO = #{deptNo}\n'
            '      AND ROWNUM <= 10\n'
            '    START WITH MGR_ID IS NULL\n'
            '    CONNECT BY PRIOR EMPNO = MGR_ID\n'
            '    ]]>\n'
            '</select>'
        )
        res = self.converter.transform_xml_content(xml)
        self.assertIn("<![CDATA[", res)
        self.assertIn("]]>\n</select>", res)
        self.assertNotIn("LIMIT 10 ]]>", res)

    def test_xml_entity_unescaping_and_indentation(self):
        xml = (
            '<select id="selectDeptSummary" parameterType="map" resultType="map">\n'
            '    SELECT DEPT_ID, DEPT_NAME, DECODE(USE_YN, \'Y\', \'사용중\', \'미사용\') AS USE_STATUS_NM, NVL(EMP_COUNT, 0) AS EMP_COUNT\n'
            '    FROM TB_DEPT\n'
            '    WHERE ROWNUM &lt;= 50\n'
            '</select>'
        )
        res = self.converter.transform_xml_content(xml)
        self.assertIn("CASE WHEN USE_YN = 'Y'", res)
        self.assertIn("COALESCE(EMP_COUNT, 0)", res)
        self.assertIn("LIMIT 50", res)
        self.assertIn("    SELECT\n", res)

    def test_nested_and_rownum_extraction(self):
        sql = "SELECT empno FROM emp WHERE deptno = #{deptNo} AND status = 'A' AND ROWNUM <= 10"
        res = self.converter.transform_single_query(sql, query_id="Q_NESTED_ROWNUM")
        self.assertIn("LIMIT 10", res.upper())
        self.assertNotIn("ROWNUM", res.upper())

    def test_include_paired_tag_expansion(self):
        xml = (
            '<mapper namespace="Emp">\n'
            '    <sql id="empCols">EMPNO, ENAME, SAL</sql>\n'
            '    <select id="selectEmpList">\n'
            '        SELECT <include refid="empCols"></include> FROM EMP\n'
            '    </select>\n'
            '</mapper>'
        )
        res = self.converter.transform_xml_content(xml)
        self.assertIn("EMPNO", res.upper())
        self.assertIn("SAL", res.upper())
        self.assertNotIn("</INCLUDE>", res.upper())

    def test_connect_by_clean_where_trailing_and(self):
        sql = (
            "SELECT EMPNO, ENAME FROM EMP\n"
            "WHERE DEPTNO = 10 AND ROWNUM <= 10\n"
            "START WITH MGR_ID IS NULL\n"
            "CONNECT BY PRIOR EMPNO = MGR_ID"
        )
        res = self.converter.transform_single_query(sql, query_id="Q_CTE_TRAILING_AND")
        self.assertIn("WITH RECURSIVE", res.upper())
        self.assertIn("DEPTNO = 10", res.upper())

    def test_mysql_to_postgres_on_duplicate_key_update(self):
        """MySQL ON DUPLICATE KEY UPDATE → PostgreSQL ON CONFLICT (pk) DO UPDATE SET + EXCLUDED 변환 테스트"""
        conv = MyBatisASTConverter(source_db="mysql", target_db="postgres", log_file=None)
        sql = (
            "INSERT INTO users (id, name, age) "
            "VALUES (1, '홍길동', 30) "
            "ON DUPLICATE KEY UPDATE "
            "name = VALUES(name), age = VALUES(age)"
        )
        res = conv.transform_single_query(sql, query_id="Q_UPSERT")
        res_upper = res.upper()
        # 1) ON CONFLICT (id) 충돌 대상 컬럼이 있어야 함
        self.assertIn("ON CONFLICT", res_upper)
        self.assertIn("(ID)", res_upper)
        # 2) DO UPDATE SET 이 정확히 한 번 있어야 함 (SET SET 중복 방지)
        self.assertNotIn("SET SET", res_upper)
        self.assertIn("DO UPDATE SET", res_upper)
        # 3) VALUES(name) → EXCLUDED.name 변환
        self.assertIn("EXCLUDED.NAME", res_upper)
        self.assertIn("EXCLUDED.AGE", res_upper)
        self.assertNotIn("VALUES(NAME)", res_upper)

    def test_postgres_to_mysql_on_conflict_to_duplicate_key(self):
        """PostgreSQL ON CONFLICT → MySQL ON DUPLICATE KEY UPDATE + VALUES() 변환 테스트"""
        conv = MyBatisASTConverter(source_db="postgres", target_db="mysql", log_file=None)
        sql = (
            "INSERT INTO users (id, name, age) "
            "VALUES (1, '홍길동', 30) "
            "ON CONFLICT (id) DO UPDATE SET "
            "name = EXCLUDED.name, age = EXCLUDED.age"
        )
        res = conv.transform_single_query(sql, query_id="Q_UPSERT_REV")
        res_upper = res.upper()
        # 1) ON DUPLICATE KEY UPDATE 로 변환되어야 함
        self.assertIn("ON DUPLICATE KEY UPDATE", res_upper)
        self.assertNotIn("ON CONFLICT", res_upper)
        # 2) EXCLUDED.col → VALUES(col) 변환
        self.assertIn("VALUES(NAME)", res_upper)
        self.assertIn("VALUES(AGE)", res_upper)
        self.assertNotIn("EXCLUDED.", res_upper)

    def test_mysql_to_postgres_upsert_edge_cases(self):
        """스키마명, 따옴표 식별자, VALUES(table.col) 등의 엣지 케이스 정합성 검토 테스트"""
        conv = MyBatisASTConverter(source_db="mysql", target_db="postgres", log_file=None)
        sql = (
            "INSERT INTO my_schema.`users` (`user_id`, `name`, `age`) "
            "VALUES (1, '홍길동', 30) "
            "ON DUPLICATE KEY UPDATE "
            "`name` = VALUES(`users`.`name`), `age` = VALUES(age)"
        )
        res = conv.transform_single_query(sql, query_id="Q_UPSERT_EDGE")
        res_upper = res.upper()
        # 1) 스키마/백틱 환경에서도 PK (USER_ID) 추출 검증
        self.assertIn("(USER_ID)", res_upper)
        # 2) VALUES(`users`.`name`) -> EXCLUDED.NAME 변환 검증
        self.assertIn("EXCLUDED.NAME", res_upper)
        self.assertIn("EXCLUDED.AGE", res_upper)

        # 컬럼 목록 없는 INSERT의 경우 TODO 힌트 주석 포함 검증
        sql_no_cols = (
            "INSERT INTO users VALUES (1, '홍길동', 30) "
            "ON DUPLICATE KEY UPDATE name = VALUES(name)"
        )
        res_no_cols = conv.transform_single_query(sql_no_cols, query_id="Q_UPSERT_NO_COLS")
        self.assertIn("/* TODO: SPECIFY PK COLUMN */", res_no_cols.upper())

if __name__ == "__main__":
    unittest.main()

