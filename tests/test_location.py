"""Tests for the Location Adapter."""
from bs4 import BeautifulSoup

from kgp_mcp.adapters.location_adapter import LocationAdapter


def test_extract_halls_from_soup():
    """Test hall + warden extraction from mocked HMC HTML."""
    html = """
    <html><body><main>
      <p>Atal Bihari Vajpayee Hall of Residence</p>
      <a>Prof. Suman Maiti</a>
      <p>Electrical Engineering</p>
      <b>WARDEN</b>
      <p>Phone: 03222-282000</p>

      <p>Azad Hall of Residence</p>
      <a>Prof. Ramesh Kumar</a>
      <p>Mechanical Engineering</p>
      <b>WARDEN</b>
    </main></body></html>
    """
    adapter = LocationAdapter(url="test", osm_client=None)
    soup = BeautifulSoup(html, "html.parser")
    halls = adapter._extract_halls_from_soup(soup)

    assert len(halls) == 2
    assert halls[0]["name"] == "Atal Bihari Vajpayee Hall of Residence"
    assert halls[0]["warden"] == "Prof. Suman Maiti"
    assert "Electrical Engineering" in halls[0]["warden_department"]
    assert halls[1]["name"] == "Azad Hall of Residence"
    assert halls[1]["warden"] == "Prof. Ramesh Kumar"


def test_clean_hall_name():
    """Test that leading prefixes are stripped."""
    assert LocationAdapter._clean_hall_name(
        "Assistant Warden. Nehru Hall of Residence"
    ) == "Nehru Hall of Residence"
    assert LocationAdapter._clean_hall_name(
        "Azad Hall of Residence"
    ) == "Azad Hall of Residence"


def test_normalize_hall_name():
    adapter = LocationAdapter(url="test", osm_client=None)
    assert adapter._normalize("Nehru Hall of Residence") == "nehru"
    assert adapter._normalize("LBS Hall") == "lbs"
    assert adapter._normalize("Vidyasagar Hall of Residence") == "vidyasagar"


def test_to_campus_entity_rich_metadata():
    adapter = LocationAdapter(url="test", osm_client=None)
    entity = adapter.to_campus_entity({
        "name": "Nehru Hall of Residence",
        "facility_type": "hostel",
        "warden": "Prof. Ramesh Kumar",
        "warden_department": "Mechanical Engineering",
        "latitude": 22.3175,
        "longitude": 87.3098,
    })
    assert entity.entity_type == "location"
    assert entity.id == "location:nehru_hall_of_residence"
    assert entity.metadata["warden"] == "Prof. Ramesh Kumar"
    assert entity.metadata["latitude"] == 22.3175