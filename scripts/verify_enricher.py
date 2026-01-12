from src.services.city_enricher import CityEnricher
import pandas as pd

def test_enricher():
    print("Initializing CityEnricher...")
    enricher = CityEnricher()
    
    # Test individual coordinate
    lat, lon = 41.3851, 2.1734 # Barcelona
    city = enricher.get_city(lat, lon)
    print(f"Coordinate ({lat}, {lon}) resolved to: {city}")
    assert city in ["Barcelona", "Ciutat Vella"], f"Expected Barcelona or Ciutat Vella, got {city}"
    
    # Test DataFrame enrichment
    data = {
        'lat': [40.4168, 48.8566, None],
        'lon': [-3.7038, 2.3522, None],
        'City': [None, 'Unknown', 'Existing']
    }
    df = pd.DataFrame(data)
    print("\nOriginal DataFrame:")
    print(df)
    
    print("\nEnriching DataFrame...")
    df = enricher.enrich_dataframe(df)
    print(df)
    
    # Madrid check
    madrid = df.iloc[0]['City']
    assert madrid == 'Madrid', f"Expected Madrid, got {madrid}"
    
    # Paris check (was Unknown)
    paris = df.iloc[1]['City']
    assert paris == 'Paris', f"Expected Paris, got {paris}"
    
    # Existing check
    existing = df.iloc[2]['City']
    assert existing == 'Existing', f"Expected Existing, got {existing}"
    
    print("\nVerification Successful!")

if __name__ == "__main__":
    test_enricher()
