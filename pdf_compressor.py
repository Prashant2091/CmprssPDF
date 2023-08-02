import streamlit as st
import fitz
import io
import base64

def compress_pdf(uploaded_file, compression_factor):
    pdf_data = uploaded_file.read()

    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
    for page_num in range(pdf_document.page_count):
        page = pdf_document.load_page(page_num)
        page.apply_compression(compression_factor)

    output_buffer = io.BytesIO()
    pdf_document.save(output_buffer, deflate=True)
    pdf_document.close()

    return output_buffer.getvalue()

def main():
    st.title("PDF Compressor")
    st.write("Upload a PDF file and choose the compression factor.")

    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

    if uploaded_file is not None:
        compression_factor = st.slider("Compression Factor", 0, 9, 5)

        if st.button("Compress and Download"):
            compressed_pdf_content = compress_pdf(uploaded_file, compression_factor)

            # Provide a custom button label and link to trigger download
            st.markdown(
                f'<a href="data:application/pdf;base64,{base64.b64encode(compressed_pdf_content).decode()}" download="compressed_pdf.pdf">Download Compressed PDF</a>',
                unsafe_allow_html=True,
            )

if __name__ == "__main__":
    main()
