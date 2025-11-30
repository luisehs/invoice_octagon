from io import BytesIO
from xhtml2pdf import pisa


def html_to_pdf_bytes(html: str) -> bytes:
    result = BytesIO()
    # pisa.CreatePDF escribe el PDF en el buffer 'result'
    pisa_status = pisa.CreatePDF(src=html, dest=result)

    if pisa_status.err:
        # Podrías lanzar una excepción si quieres manejarlo mejor
        raise RuntimeError("Error generating PDF")

    return result.getvalue()