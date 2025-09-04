# Logic for generating PDF reports
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from io import BytesIO


def create_ingredient_pdf(favor_list: list[str], avoid_list: list[str]) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = styles['h1']
    title_style.alignment = 1
    header_style = styles['h2']

    story = [Paragraph("AyushMitra Ingredient Recommendation", title_style), Spacer(1, 24)]

    # Favor Table
    story.append(Paragraph("Ingredients to Favor", header_style))
    favor_data = [[item] for item in favor_list]
    favor_table = Table(favor_data, colWidths=[400])
    favor_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.green),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(favor_table)
    story.append(Spacer(1, 24))

    # Avoid Table
    story.append(Paragraph("Ingredients to Avoid", header_style))
    avoid_data = [[item] for item in avoid_list]
    avoid_table = Table(avoid_data, colWidths=[400])
    avoid_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.red),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(avoid_table)

    doc.build(story)
    buffer.seek(0)
    return buffer


def create_recipe_plan_pdf(plan: dict) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    title_style = styles['h1']
    title_style.alignment = 1

    story = [Paragraph("AyushMitra 7-Day Recipe Plan", title_style), Spacer(1, 24)]

    plan_data = [['Day', 'Breakfast', 'Lunch', 'Dinner', 'Est. Calories']]
    for day, meals in plan.items():
        if "error" in meals: continue
        plan_data.append([day, meals['Breakfast'], meals['Lunch'], meals['Dinner'], meals['Estimated Calories']])

    table = Table(plan_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(table)

    doc.build(story)
    buffer.seek(0)
    return buffer
