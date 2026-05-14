import re
import pdfplumber


def _clean(s):
    s = (s or '').replace('\x00', 'fi')
    return re.sub(r'\s+', ' ', s).strip()


def _clean_full(text):
    return text.replace('\x00', 'fi')


def _parse_aed(s):
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
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or '')

    full = _clean_full('\n'.join(pages_text))
    p1   = _clean_full(pages_text[0] if pages_text else '')
    lines = full.split('\n')

    data = {}

    # ── Report type ───────────────────────────────────────────────────────────
    data['report_type'] = 'rent' if 'Rental Report' in full else 'sale'
    is_rent = data['report_type'] == 'rent'

    # ── Generated date ────────────────────────────────────────────────────────
    m = re.search(r'Generated on (\d+\w+ \w+ \d{4})', full)
    data['generated_date'] = m.group(1) if m else ''

    # ── Confidence ────────────────────────────────────────────────────────────
    for level in ('High Confidence', 'Medium Confidence', 'Low Confidence'):
        if level in full:
            data['confidence'] = level
            break
    else:
        data['confidence'] = 'High Confidence'

    # ── 6-month change (sale only) ────────────────────────────────────────────
    m = re.search(r'Last 6 months change\s+([+-]?\d+\.?\d*%)', full)
    data['six_month_change_str'] = m.group(1) if m else 'N/A'
    num_m = re.search(r'([+-]?\d+\.?\d*)', data['six_month_change_str'])
    data['six_month_change'] = float(num_m.group(1)) if num_m else 0.0

    # ── TruEstimate range ─────────────────────────────────────────────────────
    m = re.search(r'TruEstimate™ Range\s+AED\s*([\d\.]+[KM]?)\s*-\s*AED\s*([\d\.]+[KM]?)', full)
    data['range_low']  = _parse_aed(m.group(1)) if m else None
    data['range_high'] = _parse_aed(m.group(2)) if m else None

    # ── Price per sqft ────────────────────────────────────────────────────────
    m = re.search(r'Price per sqft\s+AED\s*([\d,]+)', full)
    raw_psf = _parse_aed(m.group(1)) if m else None
    data['price_per_sqft'] = raw_psf if raw_psf and raw_psf > 200 else None

    # ════════════════════════════════════════════════════════════════════════
    # SALE REPORT
    # ════════════════════════════════════════════════════════════════════════
    if not is_rent:
        # TruEstimate value — "TruEstimate™ Value2 AED 962,000"
        m = re.search(r'TruEstimate™\s+Value\d?\s+AED\s*([\d,]+)', full)
        data['value'] = _parse_aed(m.group(1)) if m else None

        # Rental yield embedded in newer reports: "Rent TruEstimate™ AED 60,000 / year"
        m = re.search(r'Rent TruEstimate™\s+AED\s*([\d,]+)\s*/\s*year', full)
        data['annual_rent'] = _parse_aed(m.group(1)) if m else None
        if data['annual_rent'] and data['value']:
            data['gross_yield'] = round(data['annual_rent'] / data['value'] * 100, 2)
        else:
            data['gross_yield'] = None

    # ════════════════════════════════════════════════════════════════════════
    # RENTAL REPORT
    # ════════════════════════════════════════════════════════════════════════
    else:
        data['value'] = None
        data['price_per_sqft'] = None
        data['six_month_change_str'] = 'N/A'
        data['six_month_change'] = 0.0
        data['range_low'] = None
        data['range_high'] = None

        m = re.search(r'Yearly Rent Range\s+AED\s*([\d\.]+[KM]?)\s*-\s*AED\s*([\d\.]+[KM]?)', full)
        if m:
            low  = _parse_aed(m.group(1))
            high = _parse_aed(m.group(2))
            data['range_low']   = low
            data['range_high']  = high
            data['annual_rent'] = int((low + high) / 2) if low and high else None
        else:
            data['annual_rent'] = None

        m = re.search(r'Monthly Rent Estimate\s+AED\s*([\d\.]+[KM]?)\s*-\s*AED\s*([\d\.]+[KM]?)', full)
        data['monthly_rent_low']  = _parse_aed(m.group(1)) if m else None
        data['monthly_rent_high'] = _parse_aed(m.group(2)) if m else None
        data['gross_yield'] = None

    # ── Property type ─────────────────────────────────────────────────────────
    for ptype in ('Apartment', 'Villa', 'Townhouse', 'Penthouse', 'Studio'):
        if ptype in p1:
            data['property_type'] = ptype
            break
    else:
        data['property_type'] = 'Apartment'

    # ── Building + location ───────────────────────────────────────────────────
    # Format A (multi-line): "Building Name,\nArea, Community,\nCity"
    # Format B (single line): "Building Name, Area, City"
    data['building'] = ''
    data['area']     = ''
    data['community']= ''
    data['city']     = 'Dubai'

    for ptype in ('Apartment', 'Villa', 'Townhouse', 'Studio', 'Penthouse'):
        idx = p1.find(ptype)
        if idx == -1:
            continue
        after = p1[idx + len(ptype):].strip()
        # Flatten the next few lines
        chunk = ' '.join(after.split('\n')[:5])
        chunk = re.sub(r'\s+', ' ', chunk).strip()
        # Strip noise: confidence badges, chart labels, property detail headers
        chunk = re.sub(r'\b(High|Medium|Low) Confidence\b', '', chunk)
        chunk = re.sub(r'Price per sqft.*', '', chunk)
        chunk = re.sub(r'TREND.*', '', chunk)
        chunk = re.sub(r'Property Details.*', '', chunk)
        chunk = re.sub(r'Certificate:.*', '', chunk)
        chunk = re.sub(r'©.*', '', chunk)
        chunk = re.sub(r'\s+', ' ', chunk).strip().rstrip(',')
        # Split on commas
        parts = [p.strip() for p in chunk.split(',') if p.strip()]
        if len(parts) >= 2:
            data['building'] = parts[0]
            data['city'] = parts[-1].split()[0] if parts[-1] else 'Dubai'
            data['area'] = parts[1] if len(parts) >= 2 else ''
            data['community'] = parts[2] if len(parts) >= 4 else ''
        elif len(parts) == 1:
            data['building'] = parts[0]
        break

    # ── Property details ──────────────────────────────────────────────────────
    m = re.search(r'Bedrooms\s+(Studio|\d+)', full)
    if m:
        val_beds = m.group(1)
        data['bedrooms'] = 0 if val_beds == 'Studio' else int(val_beds)
    else:
        data['bedrooms'] = 0

    m = re.search(r'Built-Up Area\s+([\d,]+)\s*sqft', full)
    data['area_sqft'] = int(m.group(1).replace(',', '')) if m else None

    m = re.search(r'Property View\s+([\w ]+?)(?:\s+\w{3} \d{4}|\s+Furnishing|\s+Unit|\n|$)', full)
    if not m:
        m = re.search(r'Property View\s+(\w+)', full)
    data['view'] = _clean(m.group(1)) if m else ''

    m = re.search(r'Furnishing Status\s+([^\n]+)', full)
    data['furnishing'] = _clean(m.group(1)) if m else ''

    m = re.search(r'Unit Number\s+(\S+)', full)
    data['unit_number'] = m.group(1) if m else ''

    # ── Cost breakdown ────────────────────────────────────────────────────────
    m = re.search(r'DLD Fee\d?\s+AED\s*([\d,]+)', full)
    data['dld_fee'] = _parse_aed(m.group(1)) if m else None

    m = re.search(r'Agency Fee\d?\s+AED\s*([\d,]+)', full)
    data['agency_fee'] = _parse_aed(m.group(1)) if m else None

    m = re.search(r'Registration Trustee Fee\d?\s+AED\s*([\d,]+)', full)
    data['registration_fee'] = _parse_aed(m.group(1)) if m else 4200

    sale_val = data.get('value') or 0
    dld    = data['dld_fee']    or int(sale_val * 0.04)
    agency = data['agency_fee'] or int(sale_val * 0.02 * 1.05)
    reg    = data['registration_fee']
    mortgage_reg = 2980
    mortgage_val = 3150
    bank_fee = round(sale_val * 0.005)

    data['dld_fee']              = dld    if dld    else None
    data['agency_fee']           = agency if agency else None
    data['mortgage_reg_fee']     = mortgage_reg
    data['mortgage_val_fee']     = mortgage_val
    data['bank_arrangement_fee'] = bank_fee if sale_val else None
    data['total_acquisition']    = int(sale_val + dld + agency + reg + mortgage_reg + mortgage_val + bank_fee) if sale_val else None

    # ── Comparable sales ──────────────────────────────────────────────────────
    # Format A (newer, single line): "4th Oct 2024 Pearlz by Danube 2 1119.88 AED 1,514,000"
    # Format B (older, 3 lines):     "11th Feb" / "Building 1 904 AED 1,050,000" / "2026"
    sales = []
    in_sales = False

    # Single-line pattern: date + address + beds + area + AED price
    single_sale_pat = re.compile(
        r'^(\d+\w+\s+\w+\s+\d{4})\s+(.+?)\s+(\d+)\s+([\d,\.]+)\s+AED\s*([\d,]+)'
    )
    # 3-line date pattern
    date_part_pat = re.compile(r'^(\d+(?:st|nd|rd|th)\s+\w+)$')

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.search(r'Recently Sold', line):
            in_sales = True
        if in_sales and re.search(r'View more|Powered by|Property History|Similar Properties', line):
            in_sales = False
        if in_sales:
            # Try single-line format first
            sm = single_sale_pat.match(line)
            if sm:
                sales.append({
                    'date':     sm.group(1).strip(),
                    'address':  sm.group(2).strip(),
                    'beds':     int(sm.group(3)),
                    'area_sqft':int(float(sm.group(4).replace(',', ''))),
                    'price':    _parse_aed(sm.group(5)),
                })
                i += 1
                continue
            # Try 3-line format
            dm = date_part_pat.match(line)
            if dm and i + 2 < len(lines):
                data_line = lines[i + 1].strip()
                year_line = lines[i + 2].strip()
                dr = re.match(r'^(.+?)\s+(\d)\s+([\d,]+)\s+AED\s*([\d,]+)$', data_line)
                yr = re.match(r'^(\d{4})$', year_line)
                if dr and yr:
                    sales.append({
                        'date':     f'{dm.group(1)} {yr.group(1)}',
                        'address':  dr.group(1).strip(),
                        'beds':     int(dr.group(2)),
                        'area_sqft':int(dr.group(3).replace(',', '')),
                        'price':    _parse_aed(dr.group(4)),
                    })
                    i += 3
                    continue
        i += 1
    data['comparable_sales'] = sales

    # ── Active listings ───────────────────────────────────────────────────────
    # Format A (newer): "Pearlz by Danube 2 2 1052 AED 1,750,000"
    # Format B (older):  split across 3 lines
    listings = []
    in_listings = False
    listing_trigger = re.compile(r'Currently Advertised For (Sale|Rent)')
    current_listing_type = 'sale'

    # Single-line listing pattern: name + beds + baths + area + AED price
    single_list_pat = re.compile(
        r'^(.+?)\s+(\d+|Studio)\s+(\d+)\s+([\d,]+)\s+AED\s*([\d,]+)'
    )

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        lt_m = listing_trigger.search(line)
        if lt_m:
            in_listings = True
            current_listing_type = lt_m.group(1).lower()
        if in_listings and re.search(r'View more|Powered by TruEstimate|Generated on', line):
            in_listings = False
        if in_listings:
            # Skip header row
            if re.match(r'^(Property|Location|Beds|Baths|Area|Listing|Rent)\b', line):
                i += 1
                continue
            # Try single-line format
            slm = single_list_pat.match(line)
            if slm:
                prop = slm.group(1).strip()
                beds_raw = slm.group(2)
                beds_val = 0 if beds_raw == 'Studio' else int(beds_raw)
                # Sanity check: price should be > 1000 (not a sqft value)
                price = _parse_aed(slm.group(5))
                if price and price > 5000:
                    listings.append({
                        'property':     prop,
                        'beds':         beds_val,
                        'baths':        int(slm.group(3)),
                        'area_sqft':    int(slm.group(4).replace(',', '')),
                        'price':        price,
                        'listing_type': current_listing_type,
                    })
                i += 1
                continue
            # Try 3-line format (older)
            data_m = re.match(r'^(\d)\s+(\d)\s+([\d,]+)\s+AED\s*([\d,]+)$', line)
            if data_m:
                name1 = lines[i - 1].strip() if i > 0 else ''
                name2 = lines[i + 1].strip() if i + 1 < len(lines) else ''
                name_parts = [p for p in [name1, name2]
                              if p and not re.match(r'^(Property|Location|Beds|Baths|Area|Listing|Rent|View more)', p)
                              and not re.match(r'^\d', p)]
                listings.append({
                    'property':     ' '.join(name_parts) or 'N/A',
                    'beds':         int(data_m.group(1)),
                    'baths':        int(data_m.group(2)),
                    'area_sqft':    int(data_m.group(3).replace(',', '')),
                    'price':        _parse_aed(data_m.group(4)),
                    'listing_type': current_listing_type,
                })
        i += 1
    data['active_listings'] = listings

    return data


if __name__ == '__main__':
    import sys, json
    result = parse(sys.argv[1])
    print(json.dumps(result, indent=2))
