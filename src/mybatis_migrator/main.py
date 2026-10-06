import argparse
import sys

from mybatis_migrator.converter import MyBatisASTConverter
from mybatis_migrator.gui import MigratorGUI


def main():
    parser = argparse.ArgumentParser(description="MyBatis XML AST DB Transpiler & GUI Migrator")
    parser.add_argument("--dir", help="변환할 XML 파일들이 위치한 폴더 (지정 시 CLI 모드로 실행)")
    parser.add_argument("--out", help="출력 폴더 (미지정 시 <dir>_converted)")
    parser.add_argument(
        "--src", default="oracle", help="Source DB Dialect (oracle, mysql, postgres 등)"
    )
    parser.add_argument(
        "--target", default="postgres", help="Target DB Dialect (postgres, oracle, mysql 등)"
    )
    parser.add_argument(
        "--log", default="migration_review.log", help="검수 대상 쿼리 로그 파일 경로"
    )
    parser.add_argument("--cli", action="store_true", help="GUI를 실행하지 않고 CLI 모드로 실행")

    args, _unknown = parser.parse_known_args()

    if args.dir or args.cli:
        if not args.dir:
            print("[오류] CLI 모드로 실행하려면 --dir 옵션으로 입력 폴더를 지정해야 합니다.")
            sys.exit(1)

        print("=== MyBatis DB Transpiler CLI 모드 실행 ===")
        print(f"입력 폴더: {args.dir}")
        print(f"출력 폴더: {args.out or '자동 지정'}")
        print(f"변환: {args.src} -> {args.target}\n")

        converter = MyBatisASTConverter(
            source_db=args.src, target_db=args.target, log_file=args.log
        )
        reviews = converter.process_directory(args.dir, args.out)
        total_cnt = converter.total_queries_count
        review_cnt = len(reviews)
        print(
            f"\n[완료] 일괄 변환 완료. (총 쿼리 카운터 / 미완료 대상 쿼리: {total_cnt} / {review_cnt})"
        )
        if reviews:
            print(f"검수 대상 쿼리 리포트가 '{args.log}' 파일에 생성되었습니다.")
    else:
        # Launch Windows GUI
        app = MigratorGUI()
        app.mainloop()


if __name__ == "__main__":
    main()
