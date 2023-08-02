import io
import PyPDF2
import streamlit as st
import base64
def compress_pdf(uploaded_file):
    pdf_reader = PyPDF2.PdfFileReader(uploaded_file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page_number in range(len(pdf_reader.pages)):
        page = pdf_reader.getPage(page_number)
        page.compressContentStreams()
        pdf_writer.addPage(page)

    compressed_pdf_bytes = io.BytesIO()
    pdf_writer.write(compressed_pdf_bytes)
    return compressed_pdf_bytes

def main():
    st.title("PDF Compressor")

    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])
    if uploaded_file is not None:
        if st.button("Compress PDF"):
            compressed_pdf = compress_pdf(uploaded_file)

            st.markdown(
                f'<a href="data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}" download="compressed.pdf">Download Compressed PDF</a>',
                unsafe_allow_html=True
            )

if __name__ == "__main__":
    main()
