import re
import pdfplumber


def _clean(s):
    # Replace null-byte ligatures (fi, fl, ff) common in PDF extractions
    s = (s or '').replace('\x00', 'fi')
    return re.sub(r'\s+', ' ', s).strip()


def _clean_full(text):
    """Normalize full text: fix ligature null bytes."""
    return text.replace('\x00', 'fi')


def _parse_aed(s):
    """Parse 'AED 1,234,567' or '1,234,567' or '1.23M' into int."""
    if not s:
        return None
    s = str(s).replace('AED', '').replace(',', '').strip()
    if s.upper().endswith('M'):
        return int(float(s[:-1]) * 1_000_000)
    if s.upper().endswith('K'):
        return int(float(s[:-1]) * 1_000)
    try:
        return int(float(s))
    except ValueError:
        return None


def parse(pdf_path: str) -> dict:
    """
    Parse a Bayut TruEstimate Sale PDF and return a structured dict.
    Handles both older and newer TruEstimate layouts.
    """
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or '')

    full = _clean_full('\n'.join(pages_text))
    p1 = _clean_full(pages_text[0] if pages_text else '')

    data = {}

    # ── Report type ──────────────────────────────────────────────────────────
    data['report_type'] = 'rent' if 'Rent Report' in full else 'sale'

    # ── Generated date ───────────────────────────────────────────────────────
    m = re.search(r'Generated on (\d+\w+ \w+ \d{4})', full)
    data['generated_date'] = m.group(1) if m else ''

    # ── Bayut agent username ─────────────────────────────────────────────────
    m = re.search(r'by (.+?) Generated on', p1)
    data['bayut_agent'] = _clean(m.group(1)) if m else ''

    # ── TruEstimate value ────────────────────────────────────────────────────
    # Appears as "TruEstimate™ Value2 AED 962,000" (² rendered as plain 2)
    m = re.search(r'TruEstimate™\s+Value\d?\s+AED\s*([\d,]+)', full)
    data['value'] = _parse_aed(m.group(1)) if m else None

    # ── Confidence ───────────────────────────────────────────────────────────
    for level in ('High Confidence', 'Medium Confidence', 'Low Confidence'):
        if level in full:
            data['confidence'] = level
            break
    else:
        data['confidence'] = 'Confidence Not Stated'

    # ── Price per sqft ───────────────────────────────────────────────────────
    m = re.search(r'Price per sqft\s+AED ([\d,]+)', full)
    data['price_per_sqft'] = _parse_aed(m.group(1)) if m else None

    # ── 6-month change ───────────────────────────────────────────────────────
    m = re.search(r'Last 6 months change\s+([+-]?\d+\.?\d*%)', full)
    data['six_month_change_str'] = m.group(1) if m else '+0.00%'
    change_num = re.search(r'([+-]?\d+\.?\d*)', data['six_month_change_str'])
    data['six_month_change'] = float(change_num.group(1)) if change_num else 0.0

    # ── TruEstimate range ────────────────────────────────────────────────────
    m = re.search(r'TruEstimate™ Range\s+AED ([\d\.]+[KM]?) - AED ([\d\.]+[KM]?)', full)
    if m:
        data['range_low'] = _parse_aed(m.group(1))
        data['range_high'] = _parse_aed(m.group(2))
    else:
        data['range_low'] = None
        data['range_high'] = None

    # ── Property type ────────────────────────────────────────────────────────
    for ptype in ('Apartment', 'Villa', 'Townhouse', 'Penthouse', 'Studio'):
        if ptype in p1:
            data['property_type'] = ptype
            break
    else:
        data['property_type'] = 'Apartment'

    # ── Building + location ──────────────────────────────────────────────────
    # Pattern: "Apartment\nBuilding Name,\nArea, Community,\nCity"
    m = re.search(
        r'(?:Apartment|Villa|Townhouse|Studio|Penthouse)\s*\n([^\n,]+),\s*\n([^\n,]+),\s*\n?([^\n,]+),?\s*\n?(\w+)',
        p1
    )
    if m:
        data['building'] = _clean(m.group(1))
        data['area'] = _clean(m.group(2))
        data['community'] = _clean(m.group(3))
        data['city'] = _clean(m.group(4))
    else:
        # Fallback: grab the next lines after property type
        lines = p1.split('\n')
        for i, line in enumerate(lines):
            if any(pt in line for pt in ('Apartment', 'Villa', 'Townhouse')):
                raw = ' '.join(lines[i+1:i+5])
                parts = [_clean(x) for x in raw.split(',')]
                data['building'] = parts[0] if len(parts) > 0 else ''
                data['area'] = parts[1] if len(parts) > 1 else ''
                data['community'] = parts[2] if len(parts) > 2 else ''
                data['city'] = parts[3] if len(parts) > 3 else 'Dubai'
                break
        else:
            data['building'] = ''
            data['area'] = ''
            data['community'] = ''
            data['city'] = 'Dubai'

    # ── Property details ─────────────────────────────────────────────────────
    m = re.search(r'Bedrooms\s+(\d+)', full)
    data['bedrooms'] = int(m.group(1)) if m else 0

    m = re.search(r'Built-Up Area\s+([\d,]+)\s*sqft', full)
    data['area_sqft'] = int(m.group(1).replace(',', '')) if m else None

    # Only grab the first word(s) before any chart text bleeds in
    m = re.search(r'Property View\s+([\w ]+?)(?:\s+\w{3} \d{4}|\s+Furnishing|\n|$)', full)
    if not m:
        m = re.search(r'Property View\s+(\w+)', full)
    data['view'] = _clean(m.group(1)) if m else ''

    m = re.search(r'Furnishing Status\s+([^\n]+)', full)
    data['furnishing'] = _clean(m.group(1)) if m else ''

    m = re.search(r'Unit Number\s+(\S+)', full)
    data['unit_number'] = m.group(1) if m else ''

    # ── Cost breakdown ───────────────────────────────────────────────────────
    m = re.search(r'DLD Fee\d?\s+AED\s*([\d,]+)', full)
    data['dld_fee'] = _parse_aed(m.group(1)) if m else None

    m = re.search(r'Agency Fee\d?\s+AED\s*([\d,]+)', full)
    data['agency_fee'] = _parse_aed(m.group(1)) if m else None

    # Compute total acquisition cost
    val = data['value'] or 0
    dld = data['dld_fee'] or (val * 0.04)
    agency = data['agency_fee'] or (val * 0.02 * 1.05)
    reg = 4200
    mortgage_reg = 2980
    mortgage_val = 3150
    bank_fee = round(val * 0.005)
    data['total_acquisition'] = int(val + dld + agency + reg + mortgage_reg + mortgage_val + bank_fee)
    data['registration_fee'] = reg
    data['mortgage_reg_fee'] = mortgage_reg
    data['mortgage_val_fee'] = mortgage_val
    data['bank_arrangement_fee'] = bank_fee
    # Round fees if not from PDF
    if not data['dld_fee']:
        data['dld_fee'] = int(dld)
    if not data['agency_fee']:
        data['agency_fee'] = int(agency)

    # ── Comparable sales ─────────────────────────────────────────────────────
    # TruEstimate PDFs split date across 3 lines:
    #   "11th Feb"  →  "Building Name beds area AED price"  →  "2026"
    sales = []
    lines = full.split('\n')
    in_sales = False
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.search(r'Recently Sold', line):
            in_sales = True
        if in_sales and re.search(r'View more|Powered by TruEstimate', line):
            break
        if in_sales:
            # Date prefix line: "11th Feb" or "3rd Mar"
            date_m = re.match(r'^(\d+(?:st|nd|rd|th)\s+\w+)$', line)
            if date_m and i + 2 < len(lines):
                data_line = lines[i + 1].strip()
                year_line = lines[i + 2].strip()
                # data line: "Building Name  beds  area  AED price"
                data_row = re.match(
                    r'^(.+?)\s+(\d)\s+([\d,]+)\s+AED\s*([\d,]+)$', data_line
                )
                year_m = re.match(r'^(\d{4})$', year_line)
                if data_row and year_m:
                    sales.append({
                        'date': f'{date_m.group(1)} {year_m.group(1)}',
                        'address': data_row.group(1).strip(),
                        'beds': int(data_row.group(2)),
                        'area_sqft': int(data_row.group(3).replace(',', '')),
                        'price': _parse_aed(data_row.group(4)),
                    })
                    i += 3
                    continue
        i += 1
    data['comparable_sales'] = sales

    # ── Active listings (for sale) ────────────────────────────────────────────
    # Property name is split: "Building\n beds baths area AED price\nRest"
    # Identify data rows: "int int int AED int" pattern
    listings = []
    in_listings = False
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.search(r'Currently Advertised For Sale', line):
            in_listings = True
        if in_listings and re.search(r'View more|Powered by TruEstimate', line):
            break
        if in_listings:
            data_m = re.match(r'^(\d)\s+(\d)\s+([\d,]+)\s+AED\s*([\d,]+)$', line)
            if data_m:
                # Name part before this line
                name_part1 = lines[i - 1].strip() if i > 0 else ''
                name_part2 = lines[i + 1].strip() if i + 1 < len(lines) else ''
                # Combine name parts, skip if they look like headers or empty
                name_parts = [p for p in [name_part1, name_part2]
                              if p and not re.match(r'^(Property|Location|Beds|Baths|Area|Listing|View more)', p)
                              and not re.match(r'^\d', p)]
                prop_name = ' '.join(name_parts) if name_parts else 'N/A'
                listings.append({
                    'property': prop_name,
                    'beds': int(data_m.group(1)),
                    'baths': int(data_m.group(2)),
                    'area_sqft': int(data_m.group(3).replace(',', '')),
                    'price': _parse_aed(data_m.group(4)),
                })
        i += 1
    data['active_listings'] = listings

    # ── Rental data (if this is a rent report or combined) ───────────────────
    data['annual_rent'] = None
    data['gross_yield'] = None
    m = re.search(r'Annual Rental[:\s]+AED\s+([\d,]+)', full)
    if m:
        data['annual_rent'] = _parse_aed(m.group(1))
    if data['annual_rent'] and data['value']:
        data['gross_yield'] = round(data['annual_rent'] / data['value'] * 100, 2)

    return data


if __name__ == '__main__':
    import sys, json
    result = parse(sys.argv[1])
    print(json.dumps(result, indent=2))
