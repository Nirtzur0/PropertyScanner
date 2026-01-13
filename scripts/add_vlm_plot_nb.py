import json
import os

notebook_path = 'notebooks/project_overview.ipynb'

def create_code_cell(source_lines):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in source_lines]
    }

def create_markdown_cell(source_lines):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in source_lines]
    }

with open(notebook_path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Define new cells
md_cell = create_markdown_cell([
    "### 3.3 VLM Description Coverage",
    "Analysis of how many listings have successfully generated Vision Language Model descriptions."
])

code_cell = create_code_cell([
    "# Check for valid VLM descriptions (not None, not 'None', and meaningful length)",
    "vlm_series = df['vlm_description'].apply(lambda x: 'With VLM' if x and str(x) != 'None' and len(str(x)) > 10 else 'Without VLM')",
    "vlm_counts = vlm_series.value_counts()",
    "",
    "plt.figure(figsize=(8, 6))",
    "colors = sns.color_palette('pastel')[0:2]",
    "plt.pie(vlm_counts, labels=vlm_counts.index, autopct='%1.1f%%', colors=colors, startangle=90)",
    "plt.title('Distribution of VLM Descriptions')",
    "plt.axis('equal')",
    "plt.show()",
    "",
    "print(\"Exact Counts:\")",
    "print(vlm_counts)"
])

# Append cells
nb['cells'].append(md_cell)
nb['cells'].append(code_cell)

with open(notebook_path, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1)

print("Notebook updated successfully.")
