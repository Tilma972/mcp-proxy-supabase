import re
path = 'c:/Users/calen/document-generator-worker/services/document_builder.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()
new_code = '''        # Use existing BC numero if available, otherwise generate
        bc_numero = qual_data.get("bc_numero")
        if not bc_numero:
            current_year = date.today().year
            import random
            bc_numero = f"{settings.bon_commande_prefix}-{current_year}-{random.randint(1, 9999):04d}"'''
text = re.sub(r'# Generate BC numero\s+current_year = date\.today\(\)\.year\s+import random\s+bc_numero = [^\n]+', new_code, text)
with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print('Done doc worker patch')