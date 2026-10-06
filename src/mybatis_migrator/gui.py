import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from mybatis_migrator.autoupdater import AutoUpdater
from mybatis_migrator.converter import MyBatisASTConverter


class MigratorGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("MyBatis DB Migration Tool (AST Transpiler) v1.0")
        self.geometry("1100x750")
        self.minsize(800, 600)

        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self._init_converter()
        self._init_updater()
        self._build_ui()

    def _init_converter(self):
        self.converter = MyBatisASTConverter(
            source_db="oracle", target_db="postgres", log_file="migration_review.csv"
        )

    def _init_updater(self):
        self.updater = AutoUpdater(
            app_name="mg",
            current_version="1.1.1",
            github_repo="kspark-prj/python-gui-monorepo",
            show_progress=True,
        )

    def _build_ui(self):
        top_frame = ttk.LabelFrame(self, text=" DB 설정 (Dialect Settings) ", padding=10)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(top_frame, text="Source DB:").pack(side=tk.LEFT, padx=(5, 2))
        self.src_db_var = tk.StringVar(value="oracle")
        self.src_db_combo = ttk.Combobox(
            top_frame,
            textvariable=self.src_db_var,
            values=MyBatisASTConverter.SUPPORTED_DIALECTS,
            width=12,
            state="readonly",
        )
        self.src_db_combo.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(top_frame, text="Target DB:").pack(side=tk.LEFT, padx=(5, 2))
        self.target_db_var = tk.StringVar(value="postgres")
        self.target_db_combo = ttk.Combobox(
            top_frame,
            textvariable=self.target_db_var,
            values=MyBatisASTConverter.SUPPORTED_DIALECTS,
            width=12,
            state="readonly",
        )
        self.target_db_combo.pack(side=tk.LEFT, padx=(0, 15))

        self.src_db_combo.bind("<<ComboboxSelected>>", self._on_db_changed)
        self.target_db_combo.bind("<<ComboboxSelected>>", self._on_db_changed)

        self.btn_update = ttk.Button(top_frame, text="🔄 업데이트 확인", command=self._check_update)
        self.btn_update.pack(side=tk.RIGHT, padx=5)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tab_manual = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_manual, text=" ✍️ 수동 쿼리 변환 ")
        self._build_tab_manual()

        self.tab_batch = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_batch, text=" 📁 폴더 일괄 변환 ")
        self._build_tab_batch()

        self.tab_review = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_review, text=" 📊 변환 미완료/검수 리포트 ")
        self._build_tab_review()

        self.tab_help = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_help, text=" 📖 사용자 가이드 & 도움말 ")
        self._build_tab_help()

        self.status_var = tk.StringVar(value="준비 완료")
        status_bar = ttk.Label(
            self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=3
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _on_db_changed(self, event=None):
        self.converter.source_db = self.src_db_var.get().lower()
        self.converter.target_db = self.target_db_var.get().lower()
        self.status_var.set(
            f"DB 설정 변경됨: {self.converter.source_db} -> {self.converter.target_db}"
        )

    def _check_update(self):
        self.status_var.set("업데이트 확인 중...")
        self.update_idletasks()
        has_update = self.updater.check_for_update()
        if not has_update:
            self.status_var.set("현재 최신 버전을 사용 중입니다.")
            messagebox.showinfo("업데이트 확인", "현재 최신 버전을 사용 중입니다.")

    # ==========================================
    # TAB 1: 수동 쿼리 편집 화면
    # ==========================================
    def _build_tab_manual(self):
        paned = ttk.PanedWindow(self.tab_manual, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        editor_paned = ttk.PanedWindow(paned, orient=tk.HORIZONTAL)
        paned.add(editor_paned, weight=3)

        # Left Panel (Input)
        input_frame = ttk.LabelFrame(editor_paned, text=" 원본 SQL / MyBatis XML ", padding=5)
        editor_paned.add(input_frame, weight=1)

        input_btn_frame = ttk.Frame(input_frame)
        input_btn_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(input_btn_frame, text="샘플 로드", command=self._load_sample_query).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(input_btn_frame, text="지우기", command=self._clear_manual_input).pack(
            side=tk.LEFT, padx=2
        )

        self.txt_input = tk.Text(input_frame, wrap=tk.NONE, undo=True, font=("Consolas", 10))
        input_vsb = ttk.Scrollbar(input_frame, orient=tk.VERTICAL, command=self.txt_input.yview)
        input_hsb = ttk.Scrollbar(input_frame, orient=tk.HORIZONTAL, command=self.txt_input.xview)
        self.txt_input.configure(yscrollcommand=input_vsb.set, xscrollcommand=input_hsb.set)

        input_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        input_hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.txt_input.pack(fill=tk.BOTH, expand=True)

        # Right Panel (Output)
        output_frame = ttk.LabelFrame(editor_paned, text=" 변환된 SQL / MyBatis XML ", padding=5)
        editor_paned.add(output_frame, weight=1)

        output_btn_frame = ttk.Frame(output_frame)
        output_btn_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(output_btn_frame, text="🚀 쿼리 변환", command=self._convert_manual_query).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(output_btn_frame, text="📋 결과 복사", command=self._copy_manual_output).pack(
            side=tk.LEFT, padx=2
        )

        self.txt_output = tk.Text(output_frame, wrap=tk.NONE, font=("Consolas", 10))
        output_vsb = ttk.Scrollbar(output_frame, orient=tk.VERTICAL, command=self.txt_output.yview)
        output_hsb = ttk.Scrollbar(
            output_frame, orient=tk.HORIZONTAL, command=self.txt_output.xview
        )
        self.txt_output.configure(yscrollcommand=output_vsb.set, xscrollcommand=output_hsb.set)

        output_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        output_hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.txt_output.pack(fill=tk.BOTH, expand=True)

        # Lower Panel (Grid & Review)
        review_frame = ttk.LabelFrame(
            paned, text=" ⚠️ 하단 출력: 변환 미완료 / 수동 검수 대상 쿼리 리포트 ", padding=5
        )
        paned.add(review_frame, weight=1)

        # 하단 그리드 전용 버튼 바 (그리드 복사 기능 추가)
        grid_btn_frame = ttk.Frame(review_frame)
        grid_btn_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Button(grid_btn_frame, text="📋 선택 행 복사", command=self._copy_grid_selection).pack(
            side=tk.LEFT, padx=2
        )

        cols = ("no", "query_id", "status", "reason")
        self.tree_manual_review = ttk.Treeview(
            review_frame, columns=cols, show="headings", height=4
        )
        self.tree_manual_review.heading("no", text="#")
        self.tree_manual_review.heading("query_id", text="Query ID")
        self.tree_manual_review.heading("status", text="구분")
        self.tree_manual_review.heading("reason", text="사유 / 미완료 원인")

        self.tree_manual_review.column("no", width=40, anchor="center")
        self.tree_manual_review.column("query_id", width=120, anchor="w")
        self.tree_manual_review.column("status", width=100, anchor="center")
        self.tree_manual_review.column("reason", width=600, anchor="w")

        tree_vsb = ttk.Scrollbar(
            review_frame, orient=tk.VERTICAL, command=self.tree_manual_review.yview
        )
        self.tree_manual_review.configure(yscrollcommand=tree_vsb.set)

        tree_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_manual_review.pack(fill=tk.BOTH, expand=True)

        # 단축키 및 우클릭 메뉴 등록
        self.tree_manual_review.bind("<Control-c>", lambda e: self._copy_grid_selection())
        self.tree_manual_review.bind("<Button-3>", self._show_grid_context_menu)

        self.grid_context_menu = tk.Menu(self, tearoff=0)
        self.grid_context_menu.add_command(
            label="선택한 항목 복사", command=self._copy_grid_selection
        )

    def _show_grid_context_menu(self, event):
        item = self.tree_manual_review.identify_row(event.y)
        if item:
            self.tree_manual_review.selection_set(item)
            self.grid_context_menu.post(event.x_root, event.y_root)

    def _copy_grid_selection(self):
        """수동 쿼리 하단 그리드에서 선택된 항목을 클립보드에 복사하는 기능"""
        selected_items = self.tree_manual_review.selection()
        if not selected_items:
            messagebox.showinfo("안내", "그리드에서 복사할 항목을 선택해주세요.")
            return

        copied_text = []
        for item in selected_items:
            values = self.tree_manual_review.item(item, "values")
            if values:
                copied_text.append("\t".join(map(str, values)))

        if copied_text:
            final_str = "\n".join(copied_text)
            self.clipboard_clear()
            self.clipboard_append(final_str)
            self.status_var.set("그리드 선택 항목이 클립보드에 복사되었습니다.")

    def _load_sample_query(self):
        sample = (
            '<select id="selectEmpList" parameterType="map" resultType="empVo">\n'
            "    <![CDATA[\n"
            "    SELECT EMPNO, ENAME, NVL(COMM, 0) AS COMM, SYSDATE AS NOW_DATE\n"
            "    FROM EMP\n"
            "    WHERE DEPTNO = #{deptNo}\n"
            "      AND ROWNUM <= 10\n"
            "    START WITH MGR_ID IS NULL\n"
            "    CONNECT BY PRIOR EMPNO = MGR_ID\n"
            "    ]]>\n"
            "</select>"
        )
        self.txt_input.delete("1.0", tk.END)
        self.txt_input.insert("1.0", sample)

    def _clear_manual_input(self):
        self.txt_input.delete("1.0", tk.END)
        self.txt_output.delete("1.0", tk.END)
        for item in self.tree_manual_review.get_children():
            self.tree_manual_review.delete(item)

    def _copy_manual_output(self):
        content = self.txt_output.get("1.0", tk.END).strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            self.status_var.set("변환 결과가 클립보드에 복사되었습니다.")
        else:
            messagebox.showinfo("안내", "복사할 변환 결과가 없습니다.")

    def _convert_manual_query(self):
        content = self.txt_input.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("경고", "변환할 쿼리나 XML 텍스트를 입력해주세요.")
            return

        self.converter.source_db = self.src_db_var.get().lower()
        self.converter.target_db = self.target_db_var.get().lower()
        self.converter.clear_reviews()

        transformed = self.converter.transform_xml_content(content, file_path="수동편집")

        self.txt_output.delete("1.0", tk.END)
        self.txt_output.insert("1.0", transformed)

        new_reviews = list(self.converter.review_items)
        manual_total = self.converter.total_queries_count
        manual_review = len(new_reviews)

        for item in self.tree_manual_review.get_children():
            self.tree_manual_review.delete(item)

        for idx, rev in enumerate(new_reviews, start=1):
            self.tree_manual_review.insert(
                "", tk.END, values=(idx, rev.query_id, rev.status, rev.reason)
            )

        self._refresh_tab_review_tree()

        self.status_var.set(
            f"수동 변환 완료! (총 쿼리 / 미완료 대상: {manual_total} / {manual_review})"
        )

    # ==========================================
    # TAB 2: 폴더 일괄 변환
    # ==========================================
    def _build_tab_batch(self):
        top_box = ttk.LabelFrame(self.tab_batch, text=" 디렉터리 경로 설정 ", padding=10)
        top_box.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top_box, text="원본 XML 폴더 경로:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.entry_input_dir = ttk.Entry(top_box, width=65)
        self.entry_input_dir.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Button(top_box, text="📂 폴더 선택", command=self._browse_input_dir).grid(
            row=0, column=2, padx=5, pady=5
        )

        ttk.Label(top_box, text="저장 폴더 경로 (선택):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.entry_output_dir = ttk.Entry(top_box, width=65)
        self.entry_output_dir.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Button(top_box, text="📂 폴더 선택", command=self._browse_output_dir).grid(
            row=1, column=2, padx=5, pady=5
        )

        top_box.columnconfigure(1, weight=1)

        act_box = ttk.Frame(self.tab_batch, padding=5)
        act_box.pack(fill=tk.X, padx=10, pady=5)

        self.btn_start_batch = ttk.Button(
            act_box, text="⚡ 일괄 변환 시작", command=self._start_batch_conversion
        )
        self.btn_start_batch.pack(side=tk.LEFT, padx=5)

        self.progress_bar = ttk.Progressbar(act_box, orient=tk.HORIZONTAL, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        log_box = ttk.LabelFrame(self.tab_batch, text=" 실행 로그 및 검수 대상 출력 ", padding=5)
        log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.txt_batch_log = tk.Text(log_box, wrap=tk.WORD, font=("Consolas", 9))
        batch_vsb = ttk.Scrollbar(log_box, orient=tk.VERTICAL, command=self.txt_batch_log.yview)
        self.txt_batch_log.configure(yscrollcommand=batch_vsb.set)
        batch_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_batch_log.pack(fill=tk.BOTH, expand=True)

    def _browse_input_dir(self):
        selected = filedialog.askdirectory(title="원본 XML 폴더 선택")
        if selected:
            self.entry_input_dir.delete(0, tk.END)
            self.entry_input_dir.insert(0, selected)

    def _browse_output_dir(self):
        selected = filedialog.askdirectory(title="저장 폴더 선택")
        if selected:
            self.entry_output_dir.delete(0, tk.END)
            self.entry_output_dir.insert(0, selected)

    def _start_batch_conversion(self):
        input_dir = self.entry_input_dir.get().strip()
        output_dir = self.entry_output_dir.get().strip()

        if not input_dir or not os.path.exists(input_dir):
            messagebox.showwarning("경고", "유효한 원본 XML 폴더 경로를 선택해주세요.")
            return

        self.btn_start_batch.configure(state=tk.DISABLED)
        self.txt_batch_log.delete("1.0", tk.END)
        self.txt_batch_log.insert(tk.END, f"=== 일괄 변환 작업 시작 ===\nInput: {input_dir}\n")

        self.converter.source_db = self.src_db_var.get().lower()
        self.converter.target_db = self.target_db_var.get().lower()
        self.converter.clear_reviews()

        def worker():
            def progress_cb(current, total, file_name):
                self.after(0, self._update_batch_progress, current, total, file_name)

            reviews = self.converter.process_directory(
                input_dir, output_dir if output_dir else None, progress_cb
            )
            self.after(0, self._on_batch_complete, reviews)

        threading.Thread(target=worker, daemon=True).start()

    def _update_batch_progress(self, current, total, file_name):
        percent = (current / total) * 100 if total > 0 else 100
        self.progress_bar["value"] = percent
        self.status_var.set(f"변환 중 ({current}/{total}): {file_name}")
        self.txt_batch_log.insert(tk.END, f"[{current}/{total}] {file_name} 처리 완료\n")
        self.txt_batch_log.see(tk.END)

    def _on_batch_complete(self, reviews):
        self.progress_bar["value"] = 100
        self.btn_start_batch.configure(state=tk.NORMAL)
        total_cnt = self.converter.total_queries_count
        review_cnt = len(reviews)
        success_cnt = len(self.converter.success_items)

        self.status_var.set(f"일괄 변환 완료! (총 쿼리 / 미완료 대상: {total_cnt} / {review_cnt})")

        self.txt_batch_log.insert(tk.END, "\n=== 일괄 변환 완료 ===\n")
        self.txt_batch_log.insert(
            tk.END, f"총 검수 카운터 / 미완료 대상 쿼리: {total_cnt} / {review_cnt}\n\n"
        )

        self.txt_batch_log.insert(
            tk.END, "============================================================\n"
        )
        self.txt_batch_log.insert(tk.END, f"[✅ 변환 성공한 Query ID 목록 ({success_cnt}건)]\n")
        self.txt_batch_log.insert(
            tk.END, "============================================================\n"
        )
        if self.converter.success_items:
            for idx, item in enumerate(self.converter.success_items, start=1):
                file_name = Path(item.file_path).name
                self.txt_batch_log.insert(
                    tk.END, f"  {idx}. [{file_name}] Query ID: '{item.query_id}'\n"
                )
        else:
            self.txt_batch_log.insert(tk.END, "  (성공한 쿼리가 없습니다.)\n")

        self.txt_batch_log.insert(
            tk.END, "\n============================================================\n"
        )
        self.txt_batch_log.insert(
            tk.END, f"[⚠️ 변환되지 않았거나 수동 검수가 필요한 쿼리 목록 ({review_cnt}건)]\n"
        )
        self.txt_batch_log.insert(
            tk.END, "============================================================\n"
        )
        if reviews:
            for idx, item in enumerate(reviews, start=1):
                file_name = Path(item.file_path).name
                self.txt_batch_log.insert(
                    tk.END,
                    f"  {idx}. [{item.status}] 파일: {file_name} | Query ID: {item.query_id}\n"
                    f"     사유: {item.reason}\n",
                )
        else:
            self.txt_batch_log.insert(tk.END, "  (미완료/검수 대상 쿼리가 없습니다.)\n")

        self.txt_batch_log.see(tk.END)
        self._refresh_tab_review_tree()
        messagebox.showinfo(
            "완료",
            f"일괄 변환이 완료되었습니다.\n총 쿼리 카운터 / 미완료 대상 쿼리: {total_cnt} / {review_cnt}",
        )

    # ==========================================
    # TAB 3: 검수 대상 쿼리 종합 리포트
    # ==========================================
    def _build_tab_review(self):
        top_btn_frame = ttk.Frame(self.tab_review, padding=5)
        top_btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(
            top_btn_frame, text="🔄 리포트 새로고침", command=self._refresh_tab_review_tree
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_btn_frame, text="💾 CSV 파일 저장", command=self._save_review_log).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(top_btn_frame, text="🧹 리포트 초기화", command=self._clear_review_list).pack(
            side=tk.LEFT, padx=5
        )

        paned = ttk.PanedWindow(self.tab_review, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tree_frame = ttk.Frame(paned)
        paned.add(tree_frame, weight=2)

        cols = ("no", "file_path", "query_id", "status", "reason")
        self.tree_all_review = ttk.Treeview(tree_frame, columns=cols, show="headings")
        self.tree_all_review.heading("no", text="#")
        self.tree_all_review.heading("file_path", text="파일명 / 경로")
        self.tree_all_review.heading("query_id", text="Query ID")
        self.tree_all_review.heading("status", text="상태")
        self.tree_all_review.heading("reason", text="미완료 / 검수 사유")

        self.tree_all_review.column("no", width=40, anchor="center")
        self.tree_all_review.column("file_path", width=220, anchor="w")
        self.tree_all_review.column("query_id", width=120, anchor="w")
        self.tree_all_review.column("status", width=100, anchor="center")
        self.tree_all_review.column("reason", width=450, anchor="w")

        tree_vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree_all_review.yview)
        tree_hsb = ttk.Scrollbar(
            tree_frame, orient=tk.HORIZONTAL, command=self.tree_all_review.xview
        )
        self.tree_all_review.configure(yscrollcommand=tree_vsb.set, xscrollcommand=tree_hsb.set)

        tree_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        tree_hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_all_review.pack(fill=tk.BOTH, expand=True)

        self.tree_all_review.bind("<<TreeviewSelect>>", self._on_review_item_selected)

        detail_frame = ttk.LabelFrame(paned, text=" 선택 쿼리 상세 내용 (원본 vs 변환) ", padding=5)
        paned.add(detail_frame, weight=2)

        detail_paned = ttk.PanedWindow(detail_frame, orient=tk.HORIZONTAL)
        detail_paned.pack(fill=tk.BOTH, expand=True)

        orig_box = ttk.LabelFrame(detail_paned, text=" 원본 쿼리 ", padding=3)
        detail_paned.add(orig_box, weight=1)
        self.txt_detail_orig = tk.Text(orig_box, wrap=tk.NONE, font=("Consolas", 9))
        self.txt_detail_orig.pack(fill=tk.BOTH, expand=True)

        conv_box = ttk.LabelFrame(detail_paned, text=" 변환 쿼리 (Fallback / AST) ", padding=3)
        detail_paned.add(conv_box, weight=1)
        self.txt_detail_conv = tk.Text(conv_box, wrap=tk.NONE, font=("Consolas", 9))
        self.txt_detail_conv.pack(fill=tk.BOTH, expand=True)

    def _refresh_tab_review_tree(self):
        for item in self.tree_all_review.get_children():
            self.tree_all_review.delete(item)

        for idx, rev in enumerate(self.converter.review_items, start=1):
            self.tree_all_review.insert(
                "", tk.END, values=(idx, rev.file_path, rev.query_id, rev.status, rev.reason)
            )

    def _on_review_item_selected(self, event=None):
        selected = self.tree_all_review.selection()
        if not selected:
            return
        item_values = self.tree_all_review.item(selected[0], "values")
        if not item_values:
            return

        idx = int(item_values[0]) - 1
        if 0 <= idx < len(self.converter.review_items):
            rev = self.converter.review_items[idx]

            self.txt_detail_orig.delete("1.0", tk.END)
            self.txt_detail_orig.insert("1.0", rev.original_query)

            self.txt_detail_conv.delete("1.0", tk.END)
            self.txt_detail_conv.insert("1.0", rev.converted_query)

    def _save_review_log(self):
        """CSV 형태로 리포트 저장하는 기능"""
        if not self.converter.review_items and not self.converter.success_items:
            messagebox.showinfo("안내", "저장할 변환 리포트가 없습니다.")
            return

        file_path = filedialog.asksaveasfilename(
            title="변환 리포트 CSV 저장",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if file_path:
            try:
                self.converter.write_full_report(file_path)
                messagebox.showinfo("성공", f"CSV 리포트가 성공적으로 저장되었습니다:\n{file_path}")
            except Exception as e:
                messagebox.showerror("오류", f"리포트 저장 실패: {e}")

    def _clear_review_list(self):
        self.converter.clear_reviews()
        self._refresh_tab_review_tree()
        self.txt_detail_orig.delete("1.0", tk.END)
        self.txt_detail_conv.delete("1.0", tk.END)
        self.status_var.set("리포트가 초기화되었습니다.")

    # ==========================================
    # TAB 4: 사용자 가이드 & 도움말
    # ==========================================
    def _build_tab_help(self):
        help_frame = ttk.LabelFrame(
            self.tab_help, text=" 📖 사용자 가이드 & 도움말 (Help / Guidelines) ", padding=10
        )
        help_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        txt_help = tk.Text(help_frame, wrap=tk.WORD, font=("Malgun Gothic", 10), padx=10, pady=10)
        help_vsb = ttk.Scrollbar(help_frame, orient=tk.VERTICAL, command=txt_help.yview)
        txt_help.configure(yscrollcommand=help_vsb.set)

        help_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        txt_help.pack(fill=tk.BOTH, expand=True)

        help_content = (
            "========================================================================================\n"
            "                 📖 SQLTranspiler (MyBatis Migrator) 사용자 가이드 & 도움말\n"
            "========================================================================================\n\n"
            "1. 개요 (Overview)\n"
            "----------------------------------------------------------------------------------------\n"
            "SQLTranspiler는 SQLGlot 엔진을 기반으로 동작하는 이기종 데이터베이스 SQL 및 MyBatis XML\n"
            "마이그레이션 자동화 도구입니다.\n\n"
            " - AST/Semantics 분석 기반 변환: 기존 정규식(Regex) 기반의 단순 치환 방식과 달리, SQL 구문\n"
            "   분석 트리(AST, Abstract Syntax Tree) 및 의미 구조 분석을 통해 구문 정확도가 높은 Dialect\n"
            "   변환을 수행합니다.\n"
            " - 주요 지원 DB: Oracle, PostgreSQL, MySQL, MariaDB, MSSQL, Snowflake, BigQuery,\n"
            "   DuckDB, Redshift, ClickHouse, SQLite, Trino, DB2 등 다수의 Dialect 간 상호 변환 지원.\n"
            " - 실무 중심 워크플로우: 변환 공수를 극대화함과 동시에 100% 자동 변환의 한계점을 Solved\n"
            "   솔직히 안내하며, 수동 검토(Manual Review)가 필요한 영역에 대해 Clear Warning을 남깁니다.\n\n\n"
            "2. 구문 유형별 변환 완성도 요약 (Dialect Transpilation Accuracy)\n"
            "----------------------------------------------------------------------------------------\n"
            " [구문 유형]                        [변환 완성도]  [주요 특징 및 비고]\n"
            " --------------------------------------------------------------------------------------\n"
            " • 표준 DML / DDL                    ~95%        SELECT, INSERT, UPDATE, DELETE, JOIN,\n"
            "                                                 UNION, CREATE TABLE 등 ANSI 표준 완벽 지원\n"
            " • 날짜/시간 & 문자열 함수           ~85-90%     TO_CHAR, TO_DATE, NVL, DECODE, SUBSTR,\n"
            "                                                 CONCAT 등 내장 함수 자동 맵핑\n"
            " • 복잡한 Analytic / Window / CTE    ~80%        ROW_NUMBER(), RANK(), OVER(PARTITION BY),\n"
            "                                                 WITH 절 등 창구 함수 변환\n"
            " • JSON / Nested Data 추출 구문       ~70%        JSON 연산자 (:, ->>, JSON_EXTRACT 등)\n"
            "                                                 DB 특화 문법 변환 (수동 검토 권장)\n"
            " • 절차형 스크립트 (PL/SQL 등)       ~20-30%     DECLARE, LOOP, IF-THEN, 저장 프로시저,\n"
            "                                                 패키지 등 (제한적 지원, 수동 작성 필요)\n\n"
            " ※ 참고: 변환 완성도는 원본 SQL의 ANSI 표준 준수 여부 및 Target DB Dialect에 따라 차이가 발생할 수 있습니다.\n\n\n"
            "3. 주의가 필요한 4가지 핵심 영역 (Manual Review Checkpoints)\n"
            "----------------------------------------------------------------------------------------\n"
            " 🚨 [1] JSON 및 중첩 구조 데이터 (JSON & Nested Data)\n"
            "   - Dialect별 추출 연산자 차이: Oracle (JSON_VALUE), Postgres (->>), BigQuery (JSON_EXTRACT_SCALAR),\n"
            "     Snowflake (data:name::string) 등 연산자 차이가 존재합니다.\n"
            "   - 검토 가이드: 변환 후 반환 타입(String vs JSON Object)이 앱 매핑 구조와 일치하는지 확인하세요.\n\n"
            " 🚨 [2] 암묵적 타입 변환 (Implicit Type Casting)\n"
            "   - MySQL/Oracle 등 유연한 DB에서 Postgres 등 엄격한 DB로 전환 시 형변환 런타임 에러 가능성.\n"
            "   - 검토 가이드: WHERE 조건절 및 연산식에서 명시적 CAST(col AS type) 적용 여부를 검토하세요.\n\n"
            " 🚨 [3] 날짜/시간 타임존 및 포맷팅 (Date/Time & Timezone Format)\n"
            "   - Dialect별 포맷 스트링 차이: Oracle/Postgres (YYYY-MM-DD HH24:MI:SS) vs MySQL/BigQuery (%Y-%m-%d %H:%i:%s)\n"
            "   - 검토 가이드: TO_CHAR / DATE_FORMAT 변환 시 대소문자 구문 및 Timezone 적용 여부를 검증하세요.\n\n"
            " 🚨 [4] 특수 함수 및 미지원 UDF (Special Functions & Custom UDFs)\n"
            "   - Target DB에 1:1 매핑 내장 함수가 없거나 커스텀 UDF인 경우 원본 구문이 유지(Fallback)됩니다.\n"
            "   - 검토 가이드: [📊 검수 리포트] 탭에서 MANUAL_REVIEW_REQUIRED 항목을 확인하고 대체 함수를 적용하세요.\n\n\n"
            "4. 변환 가이드라인 & 권장 워크플로우 (Best Practices)\n"
            "----------------------------------------------------------------------------------------\n"
            "   [STEP 1] 자동 변환 실행\n"
            "     └─ Source / Target DB 지정 후 수동/일괄 변환 실행\n"
            "   [STEP 2] 변환 로그 및 미변환 Warning 확인\n"
            "     └─ [📊 검수 리포트] 탭에서 미완료 / Fallback 쿼리 사유 수집\n"
            "   [STEP 3] Target DB의 EXPLAIN 또는 Dry-Run을 통한 문법 검증\n"
            "     └─ Target DB 개발 환경에서 EXPLAIN 실행으로 Syntax Error 1차 검증\n"
            "   [STEP 4] 정밀 수동 검토 (JSON, 날짜, 형변환 중심)\n"
            "     └─ 4가지 핵심 영역 체크포인트를 중심으로 수동 교정 후 최종 테스트\n\n\n"
            "5. 자주 묻는 질문 (FAQ)\n"
            "----------------------------------------------------------------------------------------\n"
            " Q1. 변환 시 에러가 나거나 문법이 원본 그대로 나오는 경우 어떻게 해야 하나요?\n"
            "  A. SQLGlot 파서가 해석하지 못하는 특수 구문, dynamic MyBatis XML 태그 중첩, 혹은 Target DB 대응\n"
            "     함수가 없는 경우 원본 쿼리를 유지(Fallback)하고 검수 리포트에 기록합니다. 리포트 탭의 사유(Reason)를\n"
            "     확인하고 Target DB 문법에 맞게 수동 교정해 주세요.\n\n"
            " Q2. 프로시저(Procedure)나 패키지도 변환해 주나요?\n"
            "  A. 본 도구는 SQL DML/DDL 쿼리 변환에 최적화되어 있습니다. PL/SQL 프로시저, 패키지, 변수 선언,\n"
            "     LOOP/IF 등 절차형 로직은 자동 변환 성공률이 제한적(~20-30%)이므로 수동 재작성을 권장합니다.\n"
        )

        txt_help.insert("1.0", help_content)
        txt_help.configure(state=tk.DISABLED)


def main():
    app = MigratorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
