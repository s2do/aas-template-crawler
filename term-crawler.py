import os
import re
import csv
import json
import argparse
from urllib.parse import urlparse
from collections import Counter

"""
AAS Template Crawler & Semantic Inventory Tool
----------------------------------------------
Recursively scans AAS (Asset Administration Shell) JSON/XML templates 
to perform semantic analysis and usage statistics.

OUTPUT SCHEMAS:

1. idta_stats_json.csv / idta_stats_xml.csv
   - Domain: The base URL domain (e.g., api.eclass-cdp.com).
   - Count: Total occurrences of this domain in the repo.
   - Percentage: Frequency relative to all found IRIs.

2. idta_element_types.csv
   - Element Type: The AAS modelType (e.g., Property, Operation, Qualifier).
   - Count: Number of occurrences.
   - Percentage: Frequency relative to total elements.

3. idta_glossary.csv
   - Term (idShort): The idShort identifier of the element.
   - Expanded Name: CamelCase to readable string (e.g., MaxSpeed -> Max Speed).
   - Element Types: Comma-separated list of AAS modelTypes found for this IRI.
   - IRI: The unique Resource Identifier.
   - Compatibility(P:S:C:I Ratio): Frequency distribution (Primary:Supplemental:ConceptDescriptionID:IsCaseOf).
   - Definition: The English language description field.
   - Source Files: Comma-separated list of files containing this IRI.
   - TotalCount: Sum of all occurrences.

4. idta_files_with_operations.csv
   - Filename: Name of the file containing the Operation.
   - Line Numbers: Comma-separated list of lines where "Operation" is defined.

USAGE:
    python url-crawler.py <directory_path>
"""

def expand_camel_case(text: str) -> str:
    """Safely expands CamelCase/PascalCase into readable text with spaces."""
    if not text or text == 'Unknown Term':
        return text
    # Insert space between lower/digit and upper
    s1 = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    # Insert space between sequential upper and upper-lower
    s2 = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', s1)
    return s2.replace('_', ' ').strip()

def has_operation(node) -> bool:
    """Recursively checks if a JSON tree contains any AAS Operation element."""
    if isinstance(node, dict):
        if node.get('modelType') == 'Operation':
            return True
        return any(has_operation(v) for v in node.values())
    elif isinstance(node, list):
        return any(has_operation(item) for item in node)
    return False

def extract_terms_from_json(node, filename: str) -> list:
    """Traverses a JSON tree to find all semantic IRIs and their roles."""
    terms = []
    
    def get_english_desc(desc_list):
        if not isinstance(desc_list, list): return "No definition"
        for lang_obj in desc_list:
            if isinstance(lang_obj, dict):
                if lang_obj.get('language', '').lower() in ['en', 'eng']:
                    return lang_obj.get('text', 'No definition')
        if desc_list and isinstance(desc_list[0], dict):
            return desc_list[0].get('text', 'No definition')
        return "No definition"

    def traverse(current_node):
        if isinstance(current_node, dict):
            # 1. Smarter idShort: Fallback to IRI suffix if idShort is missing
            term = current_node.get('idShort')
            
            # 2. Smarter Type Detection
            elem_type = current_node.get('modelType')
            
            # If no modelType, infer it from structural clues
            if not elem_type:
                if 'kind' in current_node: elem_type = "Qualifier"
                elif 'value' in current_node: elem_type = "Property"
                elif 'submodelElements' in current_node: elem_type = "Submodel"
                else: elem_type = "StructuralElement"

            # Use semantic IRI as a name fallback if even after inference we have "Unknown Term"
            if not term:
                keys = current_node.get('semanticId', {}).get('keys', [])
                if keys:
                    iri_val = keys[0].get('value', '')
                    # Split by slash, remove empty strings and numeric version segments
                    segments = [s for s in iri_val.split('/') if s and not s.isdigit()]
                    # Take the last valid segment (the entity name)
                    term = segments[-1] if segments else "Unnamed"
                else:
                    term = "Unknown"
            
            desc = get_english_desc(current_node.get('description', []))
            
            found_relations = []
            
            # Primary semanticId extraction
            keys = current_node.get('semanticId', {}).get('keys', [])
            if keys and isinstance(keys, list):
                iri = keys[0].get('value', '')
                if iri: found_relations.append((iri, "Primary"))
                    
            # Supplemental Semantic IDs
            for ref in current_node.get('supplementalSemanticIds', []):
                if isinstance(ref, dict):
                    keys = ref.get('keys', [])
                    if keys and isinstance(keys, list):
                        iri = keys[0].get('value', '')
                        if iri: found_relations.append((iri, "Supplemental"))

            # ConceptDescription references
            if elem_type == 'ConceptDescription':
                cd_id = current_node.get('id', '')
                if cd_id: found_relations.append((cd_id, "ConceptDescriptionID"))
                for ref in current_node.get('isCaseOf', []):
                    if isinstance(ref, dict):
                        keys = ref.get('keys', [])
                        if keys and isinstance(keys, list):
                            iri = keys[0].get('value', '')
                            if iri: found_relations.append((iri, "IsCaseOf"))

            # Save the term
            for iri, role in found_relations:
                if iri.startswith('http'):
                    terms.append({
                        'Term (idShort)': term,
                        'Expanded Name': expand_camel_case(term),
                        'Element Type': elem_type,
                        'Relation': role,
                        'IRI': iri,
                        'Definition': desc,
                        'Source File': filename
                    })
            
            # Recursion
            for v in current_node.values(): traverse(v)
        elif isinstance(current_node, list):
            for item in current_node: traverse(item)
    
    traverse(node)
    return terms

def crawl_idta_repo(repo_path: str):
    json_domain_counts, xml_domain_counts = Counter(), Counter()
    extracted_terms, operations_data = [], {}
    iri_pattern = re.compile(r'(https?://[a-zA-Z0-9.-]+(?:/[^\s"\'<>\\]*)?)')
    
    for root, _, files in os.walk(repo_path):
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith('.json'):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        content = "".join(lines)
                        for iri in iri_pattern.findall(content):
                            domain = urlparse(iri).netloc
                            if domain: json_domain_counts[domain.lower()] += 1
                        data = json.loads(content)
                        if has_operation(data):
                            op_lines = [str(i) for i, line in enumerate(lines, 1) if re.search(r'"modelType"\s*:\s*"Operation"', line)]
                            operations_data[file] = op_lines if op_lines else ["Unknown"]
                        extracted_terms.extend(extract_terms_from_json(data, file))
                except Exception: pass
            elif file.endswith('.xml'):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        for iri in iri_pattern.findall(content):
                            domain = urlparse(iri).netloc
                            if domain: xml_domain_counts[domain.lower()] += 1
                except Exception: pass
    return json_domain_counts, xml_domain_counts, extracted_terms, operations_data

def export_glossary_to_csv(terms: list, output_filename: str):
    if not terms: return
    
    # Define the order for our P:S:C:I ratio string
    # Primary, Supplemental, ConceptDescriptionID, IsCaseOf
    relation_order = ["Primary", "Supplemental", "ConceptDescriptionID", "IsCaseOf"]
    
    stats = {}
    for item in terms:
        iri = item['IRI']
        if iri not in stats:
            stats[iri] = {
                'Term (idShort)': item['Term (idShort)'], 
                'Expanded Name': item['Expanded Name'],
                'Element Types': set(), 
                'Source Files': set(), 
                'Definition': item['Definition'],
                'Counters': Counter(), # Explicit counters for every type
                'TotalCount': 0
            }
        
        # Increment explicit counter
        stats[iri]['Counters'][item['Relation']] += 1
        stats[iri]['Element Types'].add(item['Element Type'])
        stats[iri]['Source Files'].add(item['Source File'])
        stats[iri]['TotalCount'] += 1

    rows = []
    for iri, d in stats.items():
        # Build the P:S:C:I ratio string explicitly
        ratio_parts = [str(d['Counters'][rel]) for rel in relation_order]
        ratio = ":".join(ratio_parts)
        
        # Proof of summation: Check if logic is sound
        summed_count = sum(d['Counters'].values())
        if summed_count != d['TotalCount']:
            # This would only trigger if the internal counting logic is broken
            print(f"[Warning] Integrity check failed for IRI {iri}: Sum={summed_count}, Total={d['TotalCount']}")
        
        rows.append({
            'Term (idShort)': d['Term (idShort)'], 
            'Expanded Name': d['Expanded Name'],
            'Element Types': ", ".join(sorted(d['Element Types'])), 
            'IRI': iri,
            'Compatibility(P:S:C:I Ratio)': ratio, # Explicit Ratio
            'Definition': d['Definition'],
            'Source Files': ", ".join(sorted(d['Source Files'])), 
            'TotalCount': d['TotalCount']
        })

    # Sort by frequency
    rows.sort(key=lambda x: x['TotalCount'], reverse=True)
    fieldnames = ['Term (idShort)', 'Expanded Name', 'Element Types', 'IRI', 
                  'Compatibility(P:S:C:I Ratio)', 'Definition', 'Source Files', 'TotalCount']

    with open(output_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[Success] Glossary ({len(rows)} unique IRIs) exported to: {output_filename}")

def export_stats_to_csv(counts: Counter, output_filename: str, label: str):
    total = sum(counts.values())
    with open(output_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Domain", f"Count ({label})", "Percentage"])
        for d, c in counts.most_common():
            writer.writerow([d, c, f"{(c/total)*100:.2f}%" if total > 0 else "0%"])
    print(f"[Success] {label} Stats ({len(counts)} domains, {total} total) exported to: {output_filename}")

def export_types_to_csv(terms: list, output_filename: str):
    counts = Counter(t['Element Type'] for t in terms)
    total = sum(counts.values())
    with open(output_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Element Type", "Count", "Percentage"])
        for t, c in counts.most_common():
            writer.writerow([t, c, f"{(c/total)*100:.2f}%"])
    print(f"[Success] Element Types ({len(counts)} types, {total} total) exported to: {output_filename}")

def export_ops_to_csv(ops_dict: dict, output_filename: str):
    with open(output_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Filename", "Line Numbers"])
        for file in sorted(ops_dict.keys()):
            writer.writerow([file, ", ".join(ops_dict[file])])
    print(f"[Success] Operations Filter ({len(ops_dict)} files) exported to: {output_filename}")

def export_simple_glossary(terms: list, output_filename="glossary_summary.txt"):
    """
    Creates an alphabetically sorted text file of unique terms.
    Structure: (expanded_name, definition, first_iri, first_file)
    """
    # 1. Use a dictionary to keep unique entries based on Expanded Name
    unique_map = {}
    
    for item in terms:
        name = item['Expanded Name']
        # Only add to the map if we haven't seen this name before (ensures 'first' occurrence)
        if name not in unique_map:
            unique_map[name] = (
                name,
                item['Definition'],
                item['IRI'],
                item['Source File']
            )

    # 2. Sort by the Expanded Name (the first element of the tuple)
    sorted_list = sorted(unique_map.values(), key=lambda x: x[0])

    # 3. Write to a clean text file
    with open(output_filename, 'w', encoding='utf-8') as f:
        for entry in sorted_list:
            name, desc, iri, file = entry
            f.write(f"Name: {name}\n")
            f.write(f"Def:  {desc}\n")
            f.write(f"IRI:  {iri}\n")
            f.write(f"Src:  {file}\n")
            f.write("-" * 50 + "\n")
            
    print(f"[Success] Simple glossary summary ({len(sorted_list)} unique items) exported to: {output_filename}")

import json # Ensure this is at the top of your imports

def export_simple_glossary_json(terms: list, output_filename="glossary_summary.json"):
    """
    Creates an alphabetically sorted JSON file of unique terms.
    Structure: List of objects [ {name, definition, iri, source_file} ]
    """
    # 1. Dictionary to keep unique entries based on Expanded Name
    unique_map = {}
    
    for item in terms:
        name = item['Expanded Name']
        # Only add to the map if we haven't seen this name before (captures the 'first' occurrence)
        if name not in unique_map:
            unique_map[name] = {
                "name": name,
                "definition": item['Definition'],
                "iri": item['IRI'],
                "source_file": item['Source File']
            }

    # 2. Sort by Expanded Name (the 'name' key)
    sorted_list = sorted(unique_map.values(), key=lambda x: x['name'])

    # 3. Write to a clean JSON file
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(sorted_list, f, indent=4, ensure_ascii=False)
            
    print(f"[Success] JSON summary ({len(sorted_list)} unique items) exported to: {output_filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    path = os.path.expanduser(args.directory)
    if os.path.exists(path):
        j_stats, x_stats, terms, ops = crawl_idta_repo(path)
        export_stats_to_csv(j_stats, "idta_stats_json.csv", "JSON")
        export_stats_to_csv(x_stats, "idta_stats_xml.csv", "XML")
        export_types_to_csv(terms, "idta_element_types.csv")
        export_glossary_to_csv(terms, "idta_glossary.csv")
        export_ops_to_csv(ops, "idta_files_with_operations.csv")
        export_simple_glossary(terms, "glossary_summary.txt")
        export_simple_glossary_json(terms, "glossary_summary.json")
    else: print(f"Path not found: {path}")