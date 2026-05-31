import os

workspace = r"c:\Users\Mr\Desktop\NeuroWeave"

print("Searching for slices or clean_query...")
for root, dirs, files in os.walk(workspace):
    if "node_modules" in root or ".git" in root or "__pycache__" in root:
        continue
    for file in files:
        if file.endswith((".py", ".js", ".yaml")):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "clean_query" in content or "[:25]" in content or "[:20]" in content:
                        print(f"Match found in: {path}")
            except Exception as e:
                pass

