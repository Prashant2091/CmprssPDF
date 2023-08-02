import streamlit as st
import PyPDF2
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def compress_pdf(input_file, output_file):
    # Open the input PDF file in read-binary mode
    with open(input_file, 'rb') as file:
        pdf = PyPDF2.PdfFileReader(file)
        pdf_writer = PyPDF2.PdfFileWriter()

        # Create a canvas to draw on
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)

        # Create new PDF pages with reportlab canvas and add them to the pdf_writer
        for page_num in range(pdf.getNumPages()):
            page = pdf.getPage(page_num)
            can.setFillColorRGB(255, 255, 255)
            can.rect(0, 0, letter[0], letter[1], fill=1)
            can.doForm(pdf.getPage(page_num))
            can.save()
            packet.seek(0)
            new_pdf = PyPDF2.PdfFileReader(packet)
            page = new_pdf.getPage(0)
            pdf_writer.addPage(page)

        # Compress the PDF using PyPDF2
        pdf_writer.compressContentStreams()

        # Save the compressed PDF to the output file
        with open(output_file, 'wb') as output:
            pdf_writer.write(output)

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display the uploaded file details
    st.write("Uploaded file name:", uploaded_file.name)
    st.write("File size:", uploaded_file.size, "bytes")

    # Compress the PDF and save it to a temporary file
    compressed_file = "compressed_pdf.pdf"
    compress_pdf(uploaded_file, compressed_file)

    # Display download link for the compressed PDF
    st.write("Click below to download the compressed PDF:")
    st.download_button("Download Compressed PDF", compressed_file)

    # Display the compressed file size
    st.write("Compressed file size:", os.path.getsize(compressed_file), "bytes")
