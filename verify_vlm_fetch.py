
import os
import sys
from src.training.dataset import PropertyDataset
import torch

def verify_dataset_fetch():
    db_path = "data/listings.db"
    
    # Initialize dataset
    dataset = PropertyDataset(db_path=db_path, use_vlm=True)
    
    # Check if we have any listings with VLM descriptions
    processed_listings = [l for l in dataset.listings if l.get("vlm_description")]
    
    if not processed_listings:
        print("No processed listings found in dataset memory yet. (Maybe they were added after initialization?)")
        # Reload
        dataset = PropertyDataset(db_path=db_path, use_vlm=True)
        processed_listings = [l for l in dataset.listings if l.get("vlm_description")]
    
    print(f"Total listings in memory: {len(dataset.listings)}")
    print(f"Listings with VLM descriptions in memory: {len(processed_listings)}")
    
    if processed_listings:
        sample = processed_listings[0]
        print(f"\n--- Sample Listing Verification ---")
        print(f"ID: {sample['id']}")
        print(f"Title: {sample['title']}")
        print(f"VLM Description Length: {len(sample['vlm_description'])} chars")
        
        # Verify the text concatenation logic inside _get_text_embedding (manually for verification)
        title = sample.get("title") or ""
        desc = sample.get("description") or ""
        vlm = sample.get("vlm_description") or ""
        combined_text = f"{title}. {desc} {vlm}".strip()
        
        print(f"\nCombined Text Preview (first 200 chars):")
        print(combined_text[:200] + "...")
        
        # Verify the actual embedding call works
        emb = dataset._get_text_embedding(sample)
        print(f"\nEmbedding generated successfully! Shape: {emb.shape}")
        
    else:
        print("Verification failed: Could not find any listings with VLM data in dataset.")

if __name__ == "__main__":
    verify_dataset_fetch()
