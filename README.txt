Loomera Reports PDF v4.6 - full replacement

Fix 1: ranking donut center label
- Uses explicit server-side Persian count_label and center_label.
- Uses inline inset/font sizes so the center is stable even if Tailwind arbitrary classes were not compiled.

Fix 2: Windows/libgobject OSError
- Removes WeasyPrint completely from report export.
- Generates PDF with fpdf2 + uharfbuzz using the existing Yekan Bakh WOFF2 fonts and Loomera logo.
- No GTK/Pango/libgobject system installation is required.
- The existing export=csv route contract is intentionally kept, but it returns application/pdf.

Replace only the three project files included in this package, then update requirements.txt using requirements_pdf_replacement.txt.
