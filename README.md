=======================
Pdfc -- PDF Compressor
======================

Simple Python tooling to compress PDF files. This repository now includes a
Streamlit app for browser-based compression and optional metadata removal.

Streamlit App
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the app:
   ```bash
   streamlit run pdf_compressor.py
   ```
3. Upload one or more PDFs, optionally provide a password for protected files,
   and download the compressed results.

Deployment (Streamlit Community Cloud)
--------------------------------------
1. Push this repository to GitHub.
2. In Streamlit Community Cloud, select **New app** and point to this repo.
3. Set the app entry point to `pdf_compressor.py` and deploy.
4. Ensure `requirements.txt` is present so dependencies are installed.

Notes
-----
* Compression uses lossless stream compression via `PyPDF2`, which is safe for
  document content but may not shrink image-heavy PDFs as much as lossy tools.
* If you need more aggressive compression, consider preprocessing images before
  upload or using a dedicated PDF optimizer outside this app.
