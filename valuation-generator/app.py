import os
import tempfile
from pathlib import Path

from flask import Flask, render_template, request, send_file, jsonify

from parse_truestimate import parse
from generate_insights import generate
from build_html import build_html, render_pdf

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20 MB

AGENTS = [
    'Renil Roy',
    'Aamina',
    'Jasim',
    'Elena',
    'Sumaiya',
    'Abrar',
    'Mohammed',
    'Jaleel',
]


@app.route('/')
def index():
    return render_template('index.html', agents=AGENTS)


@app.route('/generate', methods=['POST'])
def generate_report():
    if 'pdf' not in request.files:
        return jsonify({'error': 'No PDF uploaded'}), 400

    file = request.files['pdf']
    agent_name = request.form.get('agent', 'Radiant Realtors')

    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Please upload a valid PDF file'}), 400

    # Save uploaded PDF to a temp file
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_in:
        file.save(tmp_in.name)
        input_path = tmp_in.name

    output_path = tempfile.mktemp(suffix='.pdf')

    try:
        # Parse → insights → HTML → PDF
        data = parse(input_path)
        insights = generate(data)
        html = build_html(data, agent_name, insights)
        render_pdf(html, output_path)

        building = data.get('building', 'Property').replace(' ', '_')
        unit = data.get('unit_number', '')
        filename = f'Radiant_Intelligence_{building}{"_" + unit if unit else ""}_{agent_name.split()[0]}.pdf'

        return send_file(
            output_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf',
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        os.unlink(input_path)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5050))
    app.run(debug=False, host='0.0.0.0', port=port)
