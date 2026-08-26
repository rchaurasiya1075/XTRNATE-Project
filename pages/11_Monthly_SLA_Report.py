def to_excel():
    out = BytesIO()
    export = show.copy()

    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        # Write main sheet
        sheet_name = selected_month[:31]
        export.to_excel(writer, index=False, sheet_name=sheet_name)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # Enable grid lines explicitly
        worksheet.hide_gridlines(2)

        # ------------------- Formats -------------------
        header_fmt = workbook.add_format(
            {
                'bg_color': '#0F172A',
                'font_color': '#FFFFFF',
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#475569',
                'font_name': 'Calibri',
                'font_size': 11,
            }
        )

        date_col_fmt = workbook.add_format(
            {
                'bg_color': '#F1F5F9',
                'font_color': '#0F172A',
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#CBD5E1',
            }
        )

        total_row_fmt = workbook.add_format(
            {
                'bg_color': '#334155',
                'font_color': '#FFFFFF',
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#0F172A',
                'font_size': 11,
            }
        )

        holiday_fmt = workbook.add_format(
            {
                'bg_color': '#FEE2E2',
                'font_color': '#991B1B',
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#FECACA',
            }
        )

        # SLA Bucket Colors
        green_fmt = workbook.add_format(
            {
                'bg_color': '#ECFDF5',
                'font_color': '#047857',
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#E2E8F0',
            }
        )
        yellow_fmt = workbook.add_format(
            {
                'bg_color': '#FFFBEB',
                'font_color': '#B45309',
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#E2E8F0',
            }
        )
        red_fmt = workbook.add_format(
            {
                'bg_color': '#FFF1F2',
                'font_color': '#BE123C',
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#E2E8F0',
            }
        )
        blue_total_fmt = workbook.add_format(
            {
                'bg_color': '#E0F2FE',
                'font_color': '#0369A1',
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#E2E8F0',
            }
        )
        purple_fmt = workbook.add_format(
            {
                'bg_color': '#F3E8FF',
                'font_color': '#6B21A8',
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#E2E8F0',
            }
        )

        zero_fmt = workbook.add_format(
            {
                'bg_color': '#F8FAFC',
                'font_color': '#94A3B8',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'border_color': '#E2E8F0',
            }
        )

        # ------------------- Apply Headers -------------------
        for col_num, col_name in enumerate(export.columns):
            worksheet.write(0, col_num, col_name, header_fmt)

        # ------------------- Apply Row/Cell Styles -------------------
        green_cols = ['< 2 HRS', '< 4 HRS', '< 8 HRS']
        yellow_cols = ['< 24 HRS']
        red_cols = ['> 24 HRS', '> 48 HRS', '> 72 HRS', 'HCIN (>24H)', 'OTT (>24H)']

        for row_idx, row in export.iterrows():
            excel_row = row_idx + 1
            is_total = str(row['DATE']).upper() == 'TOTAL'
            is_holiday_row = str(row.get('< 2 HRS', '')) == 'HOLIDAY'

            for col_idx, col_name in enumerate(export.columns):
                val = row[col_name]

                # 1. Total Row Styling
                if is_total:
                    worksheet.write(excel_row, col_idx, val, total_row_fmt)
                    continue

                # 2. Holiday Row Styling
                if is_holiday_row:
                    worksheet.write(excel_row, col_idx, val, holiday_fmt)
                    continue

                # 3. DATE Column
                if col_name == 'DATE':
                    worksheet.write(excel_row, col_idx, val, date_col_fmt)
                    continue

                # 4. Numeric Data Cell Formatting
                try:
                    num_val = int(val)
                except Exception:
                    num_val = 0

                if num_val == 0 and val != 'HOLIDAY':
                    worksheet.write(excel_row, col_idx, num_val, zero_fmt)
                elif col_name in green_cols or col_name == 'HCIN (<24H)':
                    worksheet.write(excel_row, col_idx, num_val, green_fmt)
                elif col_name in yellow_cols:
                    worksheet.write(excel_row, col_idx, num_val, yellow_fmt)
                elif col_name in red_cols:
                    worksheet.write(excel_row, col_idx, num_val, red_fmt)
                elif col_name == 'TOTAL RESOLVED':
                    worksheet.write(excel_row, col_idx, num_val, blue_total_fmt)
                elif col_name == 'OTT (<24H)':
                    worksheet.write(excel_row, col_idx, num_val, purple_fmt)
                else:
                    worksheet.write(excel_row, col_idx, val, zero_fmt)

        # Auto-fit Column Widths
        for col_idx, col_name in enumerate(export.columns):
            max_len = max(export[col_name].astype(str).map(len).max(), len(col_name)) + 4
            worksheet.set_column(col_idx, col_idx, max(max_len, 12))

        # ------------------- KPI Sheet Styling -------------------
        summary = pd.DataFrame(
            {
                'KPI': ['TOTAL RESOLVED', 'HCIN TOTAL', 'OTT / CELERITY TOTAL'],
                'Value': [totals['TOTAL RESOLVED'], hcin_kpi, ott_kpi],
            }
        )
        summary.to_excel(writer, index=False, sheet_name='KPI')

        kpi_ws = writer.sheets['KPI']
        kpi_ws.hide_gridlines(2)

        kpi_val_fmt = workbook.add_format(
            {
                'bg_color': '#EFF6FF',
                'font_color': '#1E3A8A',
                'bold': True,
                'align': 'center',
                'border': 1,
                'border_color': '#BFDBFE',
                'font_size': 12,
            }
        )
        kpi_lbl_fmt = workbook.add_format(
            {
                'bg_color': '#F1F5F9',
                'font_color': '#0F172A',
                'bold': True,
                'align': 'left',
                'border': 1,
                'border_color': '#CBD5E1',
            }
        )

        for col_num, col_name in enumerate(summary.columns):
            kpi_ws.write(0, col_num, col_name, header_fmt)

        for r_idx, r in summary.iterrows():
            kpi_ws.write(r_idx + 1, 0, r['KPI'], kpi_lbl_fmt)
            kpi_ws.write(r_idx + 1, 1, r['Value'], kpi_val_fmt)

        kpi_ws.set_column(0, 0, 25)
        kpi_ws.set_column(1, 1, 15)

    return out.getvalue()
