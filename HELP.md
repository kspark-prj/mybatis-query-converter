# 📖 SQLTranspiler (MyBatis Migrator) 사용자 가이드 & 도움말 문서

---

## 1. 개요 (Overview)

**SQLTranspiler**는 SQLGlot 엔진을 기반으로 동작하는 이기종 데이터베이스 SQL & MyBatis XML 마이그레이션 자동화 도구입니다.

- **AST/Semantics 분석 기반 변환**: 기존의 정규식(Regex) 기반 단순 문자열 치환 방식과 달리, SQL 구문 분석 트리(AST, Abstract Syntax Tree) 및 의미(Semantics) 구조 분석을 통해 구문 정확도가 높은 Dialect 변환을 수행합니다.
- **다양한 이기종 DB 지원**: Oracle, PostgreSQL, MySQL, MariaDB, MSSQL, Snowflake, BigQuery, DuckDB, Redshift, ClickHouse, SQLite, Trino, DB2 등 주요 데이터베이스 간 상호 변환을 지원합니다.
- **실무 중심 워크플로우**: 마이그레이션 자동화 공수를 극대화함과 동시에 100% 자동 변환이 불가능한 한계점을 솔직히 인지하고, 수동 검토(Manual Review)가 필요한 구문에 대해 명확한 Warning 및 Audit Log를 제공합니다.

---

## 2. 구문 유형별 변환 완성도 요약 (Dialect Transpilation Accuracy)

SQLTranspiler는 ANSI 표준 구문에 대해 매우 높은 변환율을 보이나, DB 고유의 절차형 언어나 특수 구문은 제한적으로 지원됩니다.

| 구문 유형 | 변환 완성도 | 주요 대상 구문 및 비고 |
| :--- | :---: | :--- |
| **표준 DML / DDL** | **~95%** | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `JOIN`, `UNION`, `CREATE TABLE` 등 ANSI 표준 구문 완벽 지원 |
| **날짜/시간 & 문자열 변환 함수** | **~85-90%** | `TO_CHAR`, `TO_DATE`, `NVL`, `DECODE`, `SUBSTR`, `CONCAT` 등 주요 내장 함수 자동 맵핑 |
| **복잡한 Analytic / Window 함수 & CTE** | **~80%** | `ROW_NUMBER()`, `RANK()`, `OVER(PARTITION BY...)`, `WITH` 절 등 창구 함수 및 공통 테이블 표현식 변환 |
| **JSON / Nested Data 추출 구문** | **~70%** | JSON 필드 추출 연산자 (`:`, `->>`, `JSON_EXTRACT_SCALAR` 등) DB별 특화 구문 변환 (수동 검토 권장) |
| **절차형 스크립트 (PL/SQL 등)** | **~20-30%** | `DECLARE`, `LOOP`, `IF-THEN`, 저장 프로시저, 패키지 등 절차형 로직은 제한적 지원 (수동 재작성 필요) |

> 💡 **참고:** 변환 완성도는 원본 SQL의 ANSI 표준 준수 여부 및 Target DB Dialect의 고유 제약조건에 따라 차이가 발생할 수 있습니다.

---

## 3. 주의가 필요한 4가지 핵심 영역 (Manual Review Checkpoints)

자동 변환 후 다음 4가지 핵심 영역은 데이터 엔지니어, DBA, 개발자의 정밀한 **수동 검토(Manual Review)**가 필수적입니다.

### 🚨 [1] JSON 및 중첩 구조 데이터 (JSON & Nested Data)
DB Dialect마다 JSON 데이터 접근 연산자 및 반환 데이터 타입(String vs Sub-JSON) 처리 방식에 차이가 있습니다.
- **Oracle:** `JSON_VALUE(data, '$.name')`
- **Postgres:** `data->>'name'` 또는 `jsonb_extract_path_text(data, 'name')`
- **BigQuery:** `JSON_EXTRACT_SCALAR(data, '$.name')`
- **Snowflake:** `data:name::string`
> **수동 검토 가이드:** 자동 변환 후 반환 타입이 단순 문자열인지 JSON 객체인지 애플리케이션 DTO / Entity 매핑 구조와 일치하는지 반드시 확인하세요.

### 🚨 [2] 암묵적 타입 변환 (Implicit Type Casting)
MySQL, Oracle 등 타입 변환에 유연한 DB에서 PostgreSQL과 같이 타입 검증이 엄격한 DB로 마이그레이션 시 런타임 형변환 에러가 발생할 수 있습니다.
- **예시:** 숫자형 컬럼에 대해 `WHERE emp_id = '10001'` (문자열 비교) 처리 시 Postgres는 명시적 캐스팅 없으면 오류 발생 가능.
> **수동 검토 가이드:** 조건절(WHERE) 및 연산식에서 명시적 `CAST(col AS TYPE)` 또는 `col::type` 구문 적용 여부를 검토하세요.

### 🚨 [3] 날짜/시간 타임존 및 포맷팅 (Date/Time Format & Timezone)
DB Dialect별 날짜 포맷 스트링(Format String) 표기법과 타임존 처리 방식이 다릅니다.
- **Oracle / Postgres:** `YYYY-MM-DD HH24:MI:SS`
- **MySQL / BigQuery:** `%Y-%m-%d %H:%i:%s`
> **수동 검토 가이드:** `TO_CHAR` 또는 `DATE_FORMAT` 함수 변환 시 포맷 기호 대소문자 차이 및 UTC/Local Timezone 적용 여부를 검증하세요.

### 🚨 [4] 특수 함수 및 미지원 UDF (Special Functions & Custom UDFs)
Target DB에 1:1로 일치하는 Built-in 내장 함수가 없거나, 사용자 정의 함수(UDF)가 사용된 경우 원본 구문이 그대로 유지(Fallback)되거나 Warning 로그가 생성됩니다.
> **수동 검토 가이드:** `📊 변환 미완료/검수 리포트` 탭에서 사유가 `[MANUAL_REVIEW_REQUIRED]`로 지정된 항목을 확인하고 Target DB 전용 함수로 대체하거나 커스텀 UDF를 구현하세요.

---

## 4. 변환 가이드라인 & 권장 워크플로우 (Best Practices)

안전하고 효율적인 DB 마이그레이션을 위해 아래 4단계 권장 워크플로우를 준수해 주세요.

```
+-------------------------------------------------------+
| STEP 1: 자동 변환 실행                                |
|   - Source/Target DB 선택                             |
|   - 수동 쿼리 또는 폴더 일괄 변환 실행                 |
+-------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------+
| STEP 2: 변환 로그 및 미변환 Warning 확인             |
|   - 📊 검수 리포트 탭 확인                            |
|   - 미완료/Fallback 쿼리 리스트 수집                 |
+-------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------+
| STEP 3: Target DB 문법 검증 (Dry-Run / EXPLAIN)       |
|   - Target DB 개발 환경 접속                           |
|   - EXPLAIN 또는 Dry-Run 실행으로 Syntax Error 검증   |
+-------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------+
| STEP 4: 정밀 수동 검토                                |
|   - JSON 추출, 날짜 포맷, 암묵적 캐스팅 집중 검수     |
|   - 최종 쿼리 반영 및 통합 테스트                     |
+-------------------------------------------------------+
```

1. **STEP 1: 자동 변환 실행** — Dialect를 지정한 후 수동 쿼리 또는 폴더 일괄 변환으로 1차 변환을 완료합니다.
2. **STEP 2: 변환 로그 및 미변환 Warning 확인** — 하단 그리드 및 `📊 변환 미완료/검수 리포트` 탭에서 Warning 메시지와 사유를 확인합니다.
3. **STEP 3: Target DB의 EXPLAIN / Dry-Run을 통한 문법 검증** — 변환 결과물을 Target DB 개발 서버에서 `EXPLAIN` 문으로 검증하여 구문 오류를 즉시 파악합니다.
4. **STEP 4: 정밀 수동 검토** — 3절의 4가지 체크포인트(JSON, 형변환, 날짜, 특수함수)를 중심으로 정밀 검수를 진행한 뒤 확정합니다.

---

## 5. 자주 묻는 질문 (FAQ)

### Q1. 변환 시 에러가 나거나 문법이 원본 그대로 나오는 경우 어떻게 해야 하나요?
> **A.** SQLGlot 파서가 해석하지 못하는 DB 고유 특수 구문, Dynamic MyBatis XML 태그의 복잡한 중첩, 또는 Target DB에 대응하는 내장 함수가 없는 경우 도구는 원본 쿼리를 안정적으로 유지(Fallback)하고 검수 리포트에 이력을 기록합니다. 이 경우 리포트 탭에서 해당 Query ID와 사유(Reason)를 확인하신 후, Target DB 문법에 맞게 수동 교정해 주시기 바랍니다.

### Q2. 프로시저(Procedure)나 패키지도 변환해 주나요?
> **A.** 본 도구는 SQL DML (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) 및 DDL 쿼리 변환에 최적화되어 있습니다. Oracle PL/SQL, Postgres PL/pgSQL의 저장 프로시저, 패키지, 변수 선언(`DECLARE`), Loop/If 제어문 등 절차형 스크립트는 자동 변환율이 제한적(~20-30%)입니다. 절차형 로직은 수동 리팩토링을 수행하거나 DB 전용 마이그레이션 툴 사용을 권장합니다.
