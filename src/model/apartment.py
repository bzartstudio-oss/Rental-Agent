from dataclasses import dataclass, field


@dataclass
class Apartment:
    title: str = ""
    price: float = 0
    currency: str = ""
    address: str = ""
    city: str = ""
    country: str = ""

    bedrooms: int = 0
    single_room: int = 0
    shared_room: int = 0
    bathrooms: int = 0
    private_bathroom: int = 0
    shared_bathroom: int = 0
    flatmates: int = 0
    

    furnished: bool = False
    air_conditioning: bool = False
    room_air_conditioning: bool = False
    parking: bool = False

    website: str = ""
    listing_url: str = ""

    walking_minutes: int = 0

    nearby_places: list = field(default_factory=list)

    score: float = 0