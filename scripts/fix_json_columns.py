import sqlite3
import json
import ast

def fix_db(db_path="data/listings.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print(f"Scanning {db_path}...")
    
    # Get all rows
    cursor.execute("SELECT id, image_urls, tags, address_full FROM listings")
    rows = cursor.fetchall()
    
    fixed_count = 0
    
    for row in rows:
        updates = {}
        
        # Check image_urls
        img_val = row['image_urls']
        if img_val and isinstance(img_val, str):
            if img_val.startswith("['") or img_val.startswith("[\""):
                try:
                    # Try standard JSON first
                    json.loads(img_val)
                except json.JSONDecodeError:
                    # Try literal eval (fixes single quotes)
                    try:
                        valid_list = ast.literal_eval(img_val)
                        json_str = json.dumps(valid_list)
                        updates['image_urls'] = json_str
                    except:
                        pass
        
        # Check tags
        tags_val = row['tags']
        if tags_val and isinstance(tags_val, str) and len(tags_val) > 2:
             if tags_val.startswith("["):
                try:
                     json.loads(tags_val)
                except:
                    try:
                        valid_list = ast.literal_eval(tags_val)
                        updates['tags'] = json.dumps(valid_list)
                    except:
                        pass

        if updates:
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            params = list(updates.values()) + [row['id']]
            cursor.execute(f"UPDATE listings SET {set_clause} WHERE id = ?", params)
            fixed_count += 1
            
    conn.commit()
    conn.close()
    print(f"Fixed {fixed_count} rows.")

if __name__ == "__main__":
    fix_db()
