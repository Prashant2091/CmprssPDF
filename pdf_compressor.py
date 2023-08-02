import streamlit as st
import PyPDF2
import io

def compress_pdf(file, compression_factor):
    pdf_reader = PyPDF2.PdfFileReader(file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page_num in range(pdf_reader.getNumPages()):
        page = pdf_reader.getPage(page_num)
        page.scaleBy(compression_factor)  # Adjust the compression factor as needed
        pdf_writer.addPage(page)

    compressed_pdf = io.BytesIO()
    pdf_writer.write(compressed_pdf)
    return compressed_pdf

def main():
    st.title('PDF Compressor')
    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

    if uploaded_file is not None:
        st.write("Original File Size: ", round(uploaded_file.size/1024, 2), "KB")

        compression_factor = st.slider("Compression Factor", min_value=0.1, max_value=1.0, step=0.1, value=0.5)

        if st.button("Compress PDF"):
            compressed_pdf = compress_pdf(uploaded_file, compression_factor)
            st.write("Compressed File Size: ", round(compressed_pdf.getbuffer().nbytes/1024, 2), "KB")
            st.download_button("Download Compressed PDF", data=compressed_pdf, file_name="compressed_pdf.pdf", mime="application/pdf")

if __name__ == "__main__":
    main()
