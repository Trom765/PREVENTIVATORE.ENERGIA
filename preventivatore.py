#!/usr/bin/env python3
import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def italian_number(value: str) -> float:
    value = value.strip().replace('€', '').replace('%', '').replace(' ', '')
    if value == '' or value == '-':
        return 0.0
    normalized = value.replace('.', '').replace(',', '.')
    try:
        return float(normalized)
    except ValueError:
        raise ValueError(f"Non è possibile convertire il valore numerico: {value}")


def find_text(pattern: str, text: str, flags=0) -> Optional[str]:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def round_money(value: float) -> float:
    return round(value + 1e-9, 2)


def parse_billing_period(text: str) -> int:
    days_match = find_text(r"(\d{1,3})\s*giorni", text, re.I)
    if days_match:
        return int(days_match)
    months_match = find_text(r"(\d{1,2})\s*mesi", text, re.I)
    if months_match:
        return int(months_match) * 30 + int(round(int(months_match) * 0.5))
    return 30


def extract_invoice_data(pdf_path: Path) -> Dict[str, object]:
    reader = PdfReader(pdf_path)
    text = '\n'.join((page.extract_text() or '') for page in reader.pages)
    text = text.replace('\xa0', ' ')

    pod = find_text(r"Punto di Prelievo \(POD\):\s*(IT[0-9A-Z]+)", text, re.I) or ''
    power_kw = italian_number(find_text(r"Potenza Impegnata:\s*([\d\.,]+)\s*kW", text, re.I) or '0')
    address = find_text(r"Indirizzo Fornitura:\s*([^\n\r]+)", text, re.I) or ''

    consumption_kwh = italian_number(find_text(r"QUOTA PER CONSUMI\s*([0-9\.,]+)\s*kWh", text, re.I) or '0')
    consumption_price = italian_number(find_text(r"QUOTA PER CONSUMI[\s\S]*?([0-9\.,]+)\s*€/kWh", text, re.I) or '0')
    consumption_total = italian_number(find_text(r"QUOTA PER CONSUMI[\s\S]*?([0-9\.,]+)\s*€", text, re.I) or '0')

    consumption_sales = italian_number(find_text(r"spesa per la vendita di energia elettrica\s*([0-9\.,]+)\s*€/kWh\s*([0-9\.,]+)\s*€", text, re.I) or '0')
    consumption_network = italian_number(find_text(r"spesa per la rete e gli oneri generali di sistema\s*([0-9\.,]+)\s*€/kWh\s*([0-9\.,]+)\s*€", text, re.I) or '0')

    fixed_months = italian_number(find_text(r"QUOTA FISSA\s*(\d+)\s*mesi", text, re.I) or '0')
    fixed_monthly = italian_number(find_text(r"QUOTA FISSA[\s\S]*?([0-9\.,]+)\s*€/mese", text, re.I) or '0')
    fixed_total = italian_number(find_text(r"QUOTA FISSA[\s\S]*?([0-9\.,]+)\s*€", text, re.I) or '0')
    fixed_network = italian_number(find_text(r"QUOTA FISSA[\s\S]*?spesa per la rete e gli oneri generali di sistema\s*([0-9\.,]+)\s*€/mese\s*([0-9\.,]+)\s*€", text, re.I) or '0')
    fixed_sales = italian_number(find_text(r"QUOTA FISSA[\s\S]*?spesa per la vendita di energia elettrica\s*([0-9\.,]+)\s*€/mese\s*([0-9\.,]+)\s*€", text, re.I) or '0')

    power_kw_value = italian_number(find_text(r"QUOTA POTENZA\s*([0-9\.,]+)\s*kW", text, re.I) or '0')
    power_months = italian_number(find_text(r"QUOTA POTENZA[\s\S]*?x\s*(\d+)\s*mesi", text, re.I) or '0')
    power_rate = italian_number(find_text(r"QUOTA POTENZA[\s\S]*?([0-9\.,]+)\s*€/kW/mese", text, re.I) or '0')
    power_total = italian_number(find_text(r"QUOTA POTENZA[\s\S]*?([0-9\.,]+)\s*€", text, re.I) or '0')

    bonus_social = italian_number(find_text(r"Bonus Sociale.*?([\-0-9\.,]+)\s*€", text, re.I) or '0')
    total_baseline = italian_number(find_text(r"Totale Bolletta.*?([0-9\.,]+)\s*€", text, re.I | re.S) or '0')

    transparent_costs = italian_number(find_text(r"Spesa Rete, Oneri di Sistema e Potenza.*?([0-9\.,]+)\s*€", text, re.I) or '0')
    if transparent_costs == 0:
        transparent_costs = round_money(consumption_network + fixed_network + power_total)

    billing_days = parse_billing_period(text)

    return {
        'pod': pod,
        'power_kw': power_kw,
        'address': address,
        'energy_kwh': consumption_kwh,
        'consumption_price': consumption_price,
        'consumption_total': consumption_total,
        'consumption_sales': consumption_sales,
        'consumption_network': consumption_network,
        'fixed_months': int(fixed_months),
        'fixed_monthly': fixed_monthly,
        'fixed_total': fixed_total,
        'fixed_network': fixed_network,
        'fixed_sales': fixed_sales,
        'power_kw_value': power_kw_value,
        'power_months': int(power_months),
        'power_rate': power_rate,
        'power_total': power_total,
        'bonus_social': bonus_social,
        'transparent_costs': transparent_costs,
        'billing_days': billing_days,
        'total_baseline': total_baseline,
    }


def calculate_offer(invoice: Dict[str, object], energy_price: float, monthly_fee: float) -> Dict[str, object]:
    energy_cost = round_money(invoice['energy_kwh'] * energy_price)
    commercialization_cost = round_money(monthly_fee * invoice['billing_days'] / 30.4375)
    transparent_costs = invoice['transparent_costs']
    accise = round_money(invoice['energy_kwh'] * 0.0125)
    iva_base = energy_cost + commercialization_cost + transparent_costs + accise
    iva = round_money(iva_base * 0.22)
    total = round_money(energy_cost + commercialization_cost + transparent_costs + accise + iva + invoice['bonus_social'])

    return {
        'energy_price': round_money(energy_price),
        'energy_cost': energy_cost,
        'commercialization_cost': commercialization_cost,
        'transparent_costs': transparent_costs,
        'accise': accise,
        'iva': iva,
        'bonus_social': invoice['bonus_social'],
        'total': total,
        'days': invoice['billing_days'],
        'monthly_fee': monthly_fee,
    }


def format_eur(value: float) -> str:
    sign = '-' if value < 0 else ''
    absolute = abs(value)
    formatted = f"{absolute:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"{sign}{formatted} €"


def build_paragraph_style(name: str, **kwargs) -> ParagraphStyle:
    base = getSampleStyleSheet()['BodyText']
    base = ParagraphStyle(name, parent=base, **kwargs)
    return base


def generate_pdf(output_path: Path, invoice: Dict[str, object], fix_offer: Dict[str, object], flex_offer: Dict[str, object], pun: float) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    heading = build_paragraph_style('Heading', fontSize=18, leading=22, spaceAfter=12, textColor=colors.HexColor('#1a1a1a'))
    section = build_paragraph_style('Section', fontSize=12, leading=16, spaceAfter=8, textColor=colors.HexColor('#333333'))
    normal = build_paragraph_style('Normal', fontSize=10.5, leading=14, spaceAfter=6)
    small = build_paragraph_style('Small', fontSize=9, leading=12, spaceAfter=4)

    def make_table(rows, col_widths=None, header=False):
        table = Table(rows, colWidths=col_widths, hAlign='LEFT')
        style = [
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#222222')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        if header:
            style.extend([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f3f3')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#000000')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('LINEABOVE', (0, 0), (-1, 0), 1, colors.HexColor('#bbbbbb')),
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#bbbbbb')),
            ])
        else:
            style.append(('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')))
        table.setStyle(TableStyle(style))
        return table

    elements = [Paragraph('Preventivo luce residenziale - analisi e confronto', heading)]
    elements.append(Paragraph('Dati identificativi e baseline estratta da fattura energetica', section))

    baseline_rows = [
        ['POD', invoice['pod']],
        ['Indirizzo di fornitura', invoice['address']],
        ['Potenza impegnata', f"{invoice['power_kw']} kW"],
        ['Periodo di fatturazione', f"{invoice['billing_days']} giorni"],
        ['Consumo rilevato', f"{invoice['energy_kwh']:,.0f}".replace(',', '.') + ' kWh'],
        ['Totale bolletta baseline', format_eur(invoice['total_baseline'])],
    ]
    elements.append(make_table(baseline_rows, col_widths=[100 * mm, 70 * mm]))
    elements.append(Spacer(1, 10))

    baseline_breakdown = [
        ['Voce', 'Valore'],
        ['Quota Consumi', f"{format_eur(invoice['consumption_total'])} ({invoice['energy_kwh']:,.0f} kWh @ {format_eur(invoice['consumption_price'])}/kWh)"],
        ['Spesa vendita energia', format_eur(invoice['consumption_sales'])],
        ['Spesa rete e oneri consumo', format_eur(invoice['consumption_network'])],
        ['Quota fissa totale', format_eur(invoice['fixed_total'])],
        ['Quota potenza totale', format_eur(invoice['power_total'])],
        ['Costi rete, oneri e potenza trasparenti', format_eur(invoice['transparent_costs'])],
        ['Bonus sociale', format_eur(invoice['bonus_social'])],
    ]
    elements.append(Paragraph('Dettaglio Baseline', section))
    elements.append(make_table(baseline_breakdown, col_widths=[100 * mm, 70 * mm], header=True))
    elements.append(Spacer(1, 16))

    def offer_section(title: str, offer: Dict[str, object], description: str):
        elements.append(Paragraph(title, heading))
        elements.append(Paragraph(description, section))
        rows = [
            ['Voce', 'Importo'],
            [f"Energia ({invoice['energy_kwh']:,.0f} kWh @ {format_eur(offer['energy_price'])}/kWh)", format_eur(offer['energy_cost'])],
            [f"Commercializzazione ({format_eur(offer['monthly_fee'])}/mese × {offer['days']} giorni)", format_eur(offer['commercialization_cost'])],
            ['Costi rete, oneri e potenza (invariati)', format_eur(offer['transparent_costs'])],
            ['Accise', format_eur(offer['accise'])],
            ['IVA 22%', format_eur(offer['iva'])],
            ['Bonus sociale', format_eur(offer['bonus_social'])],
            ['Totale offerta', format_eur(offer['total'])],
        ]
        elements.append(make_table(rows, col_widths=[100 * mm, 70 * mm], header=True))
        elements.append(Spacer(1, 14))

    offer_section(
        'Offerta Residenziale FIX',
        fix_offer,
        'Prezzo energia bloccato a 0,16 €/kWh; commercializzazione 8,00 €/mese riproporzionata sul periodo.',
    )
    offer_section(
        'Offerta Residenziale FLEX',
        flex_offer,
        f'Prezzo energia variabile: PUN {format_eur(pun)} + 0,026 €/kWh = {format_eur(round_money(pun + 0.026))}/kWh; commercializzazione 8,00 €/mese riproporzionata sul periodo.',
    )

    results_rows = [
        ['Scenario', 'Totale periodo', 'Risparmio netto vs baseline', 'Risparmio annuo stimato'],
        ['Baseline corrente', format_eur(invoice['total_baseline']), '-', '-'],
        ['Residenziale FIX', format_eur(fix_offer['total']), format_eur(invoice['total_baseline'] - fix_offer['total']), format_eur(round_money((invoice['total_baseline'] - fix_offer['total']) * 365 / invoice['billing_days']))],
        ['Residenziale FLEX', format_eur(flex_offer['total']), format_eur(invoice['total_baseline'] - flex_offer['total']), format_eur(round_money((invoice['total_baseline'] - flex_offer['total']) * 365 / invoice['billing_days']))],
    ]
    elements.append(Paragraph('Tabella comparativa finale', heading))
    table = make_table(results_rows, col_widths=[70 * mm, 45 * mm, 45 * mm, 45 * mm], header=True)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#faf7e2')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f2fff5')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#eff8ff')),
    ]))
    elements.append(table)

    doc.build(elements)


def main() -> None:
    parser = argparse.ArgumentParser(description='Preventivatore energetico per utenze residenziali.')
    parser.add_argument('--input', '-i', type=Path, default=Path('Fastweb_Vodafone_Business_Fix_Flex.pdf'), help='PDF di bolletta da analizzare')
    parser.add_argument('--output', '-o', type=Path, default=Path('preventivo.pdf'), help='PDF di preventivo generato')
    parser.add_argument('--pun', type=float, default=0.13, help='Valore PUN di riferimento per l’opzione FLEX')
    parser.add_argument('--monthly-fee', type=float, default=8.0, help='Quota commercializzazione mensile per le offerte')
    args = parser.parse_args()

    invoice = extract_invoice_data(args.input)
    fix_offer = calculate_offer(invoice, energy_price=0.16, monthly_fee=args.monthly_fee)
    flex_offer = calculate_offer(invoice, energy_price=args.pun + 0.026, monthly_fee=args.monthly_fee)

    generate_pdf(args.output, invoice, fix_offer, flex_offer, args.pun)
    print(f"Preventivo generato in: {args.output}")


if __name__ == '__main__':
    main()
