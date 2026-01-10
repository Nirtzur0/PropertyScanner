import streamlit as st
import pandas as pd
from src.services.storage import StorageService
from src.services.valuation import ValuationService
from src.services.retrieval import CompRetriever
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.core.domain.models import DBListing

# Page Config
st.set_page_config(page_title="Property Scanner Scout", layout="wide", page_icon="🏠")

@st.cache_resource
def get_services():
    storage = StorageService()
    valuation = ValuationService(storage)
    retriever = CompRetriever()
    return storage, valuation, retriever

storage, valuation, retriever = get_services()

st.title("🏠 Property Scanner Scout")

# --- Sidebar Filters ---
st.sidebar.header("Filters")
min_price, max_price = st.sidebar.slider("Price Range (€)", 0, 2000000, (100000, 1000000), step=10000)
min_score = st.sidebar.slider("Min Deal Score", 0.0, 1.0, 0.5, step=0.05)

# --- Load Data ---
session = storage.get_session()
df = pd.DataFrame()
try:
    # Fetch all listings
    listings_db = session.query(DBListing).all()
    
    # Convert to Domain Objects & Score on the Fly
    data = []
    
    # Initialize progress bar for nice UX
    if listings_db:
        progress_bar = st.progress(0, text="Analyzing Opportunities...")
    
    for i, db_item in enumerate(listings_db):
        # Reconstruct Canonical (simplified)
        loc = GeoLocation(lat=db_item.lat, lon=db_item.lon, address_full=db_item.address_full) if db_item.lat else None
        
        listing = CanonicalListing(
            id=db_item.id,
            source_id=db_item.source_id,
            external_id=db_item.external_id,
            url=str(db_item.url),
            title=db_item.title,
            price=db_item.price,
            bedrooms=db_item.bedrooms,
            surface_area_sqm=db_item.surface_area_sqm,
            location=loc,
            image_urls=db_item.image_urls
        )
        
        # Retrieval
        comps = retriever.retrieve_comps(listing, k=3)
        
        # Valuation (with Comps)
        analysis = valuation.evaluate_deal(listing, comps=comps)
        
        data.append({
            "ID": listing.id,
            "Title": listing.title,
            "Price": listing.price,
            "Sqm": listing.surface_area_sqm,
            "Bedrooms": listing.bedrooms,
            "City": db_item.city,
            "Deal Score": analysis.deal_score,
            "Fair Value": analysis.fair_value_estimate,
            "Thesis": analysis.investment_thesis,
            "URL": listing.url,
            "lat": listing.location.lat if listing.location else None,
            "lon": listing.location.lon if listing.location else None,
            "Image": listing.image_urls[0] if listing.image_urls else None,
            "Comps": comps # Store for UI
        })
        
        if listings_db:
            progress_bar.progress((i + 1) / len(listings_db))
        
    df = pd.DataFrame(data)
    if listings_db:
        progress_bar.empty()

finally:
    session.close()

if df.empty:
    st.warning("No listings found in database.")
else:
    # --- Filter Data ---
    filtered_df = df[
        (df["Price"] >= min_price) & 
        (df["Price"] <= max_price) &
        (df["Deal Score"] >= min_score)
    ]

    # --- KPIs ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Listings Found", len(filtered_df))
    if not filtered_df.empty:
        c2.metric("Avg Price", f"{filtered_df['Price'].mean():,.0f} €")
        c3.metric("Top Deal Score", f"{filtered_df['Deal Score'].max():.2f}")

    # --- Tabs ---
    tab1, tab2 = st.tabs(["🗺️ Map View", "📄 List View"])

    with tab1:
        # Streamlit Map requires lat/lon columns and no NaNs
        map_data = filtered_df.dropna(subset=['lat', 'lon'])
        if not map_data.empty:
            st.map(map_data, size=20, color="#00ff00") # Green dots
        else:
            st.info("No geocoded listings to display on map. (Are you running 'IdealistaNormalizer' correctly?)")

    with tab2:
        # Display Table with key columns
        display_cols = ["Title", "Price", "Sqm", "Deal Score", "Fair Value", "Thesis", "URL"]
        st.dataframe(
            filtered_df[display_cols].style.format({
                "Price": "{:,.0f} €", 
                "Fair Value": "{:,.0f} €",
                "Deal Score": "{:.2f}", 
                "Sqm": "{:.0f}"
            }),
            use_container_width=True
        )

    # --- Details Section ---
    st.markdown("---")
    st.subheader("🧐 Deal Inspector")
    
    if not filtered_df.empty:
        selected_id = st.selectbox("Select Property to Inspect", filtered_df["Title"].unique())
        if selected_id:
            item = filtered_df[filtered_df["Title"] == selected_id].iloc[0]
            
            c_left, c_right = st.columns([1, 2])
            
            with c_left:
                if item["Image"]:
                    st.image(item["Image"], use_column_width=True)
                else:
                    st.markdown("📷 *No Image Available*")
                    
            with c_right:
                st.write(f"**Price:** {item['Price']:,.0f} €")
                st.write(f"**Fair Value:** {item['Fair Value']:,.0f} €")
                st.write(f"**Score:** {item['Deal Score']:.2f}")
                st.info(item["Thesis"])
                st.markdown(f"[View on Idealista]({item['URL']})")
                
                # Show Comps
                if item["Comps"]:
                    with st.expander(f"📚 Evidence: {len(item['Comps'])} Comparable Listings"):
                        for c in item["Comps"]:
                            st.markdown(f"- **{c.similarity_score:.0%} Sim**: {c.price:,.0f}€ ({c.features.get('sqm')}m²) [Snap: {c.id[:8]}]")
