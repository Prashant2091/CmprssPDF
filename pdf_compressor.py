import streamlit as st
import PyPDF2
import io

def compress_pdf(input_file):
    pdf_reader = PyPDF2.PdfReader(input_file)
    pdf_writer = PyPDF2.PdfWriter()

    for page in pdf_reader.pages:
        pdf_writer.add_page(page)
    
    # Set compression options for content streams
    pdf_writer.compressContentStreams(compression_level=5)
    
    compressed_pdf = io.BytesIO()
    pdf_writer.write(compressed_pdf)
    compressed_pdf.seek(0)
    
    return compressed_pdf

def main():
    st.title("PDF Compressor")

    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])
    if uploaded_file:
        compressed_pdf = compress_pdf(uploaded_file)

        st.markdown(f'<a href="data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}" download="compressed.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
