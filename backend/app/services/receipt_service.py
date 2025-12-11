from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from datetime import datetime
from app.db.models.payment import Payment
from app.db.models.invoice import Invoice
from app.db.models.repair_order import RepairOrder
from io import BytesIO


def generate_receipt_pdf(payment: Payment, invoice: Invoice, repair_order: RepairOrder) -> BytesIO:
    """Generate a PDF receipt for a payment"""
    
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Header
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, height - 50, "TRUCK PIT STOP")
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 70, "Receipt")
    
    # Payment details
    y = height - 120
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Payment Details")
    
    y -= 25
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Receipt Number: {payment.payment_number}")
    y -= 15
    c.drawString(50, y, f"Date: {payment.created_at.strftime('%B %d, %Y')}")
    y -= 15
    c.drawString(50, y, f"Amount: ${float(payment.amount):.2f}")
    y -= 15
    c.drawString(50, y, f"Method: {payment.method.value}")
    y -= 15
    c.drawString(50, y, f"Status: {payment.status.value}")
    
    # Repair order info
    y -= 30
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Repair Order")
    y -= 25
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Order Number: {repair_order.order_number}")
    
    # Footer
    c.setFont("Helvetica", 8)
    c.drawString(50, 50, "Thank you for your business!")
    
    c.save()
    buffer.seek(0)
    return buffer

