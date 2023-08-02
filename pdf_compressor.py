import streamlit as st
import PyPDF2
import io

def compress_pdf(input_pdf, compression_factor):
    # Create a PDF writer object
    pdf_writer = PyPDF2.PdfWriter()

    # Open the input PDF file
    with open(input_pdf, "rb") as pdf_file:
        # Create a PDF reader object
        pdf_reader = PyPDF2.PdfFileReader(pdf_file)

        # Get the total number of pages in the PDF
        total_pages = pdf_reader.getNumPages()

        # Process each page
        for page_num in range(total_pages):
            # Get the current page
            page = pdf_reader.getPage(page_num)

            # Apply compression to the page
            page.compressContentStreams(compression_factor)

            # Add the compressed page to the PDF writer
            pdf_writer.addPage(page)

        # Write the compressed PDF to a BytesIO buffer
        output_buffer = io.BytesIO()
        pdf_writer.write(output_buffer)

    return output_buffer

def main():
    st.title("PDF Compressor")

    # File uploader widget
    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

    if uploaded_file is not None:
        # Get the compression factor from the user
        compression_factor = st.slider("Select Compression Factor", min_value=0, max_value=100, value=50)

        # Check if the user clicked the "Compress" button
        if st.button("Compress"):
            # Compress the PDF
            compressed_pdf = compress_pdf(uploaded_file, compression_factor)

            # Download the compressed PDF
            st.download_button("Download Compressed PDF", data=compressed_pdf.getvalue(), file_name="compressed.pdf")

if __name__ == "__main__":
    main()
