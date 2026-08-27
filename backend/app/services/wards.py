from functools import lru_cache

import httpx

GCC_WARD_SERVICE = 'https://gisgcc.chennaicorporation.gov.in/server/rest/services/GCCDepts/EDPMobile2025/FeatureServer/2/query'
GCC_WARD_SOURCE = 'https://gisgcc.chennaicorporation.gov.in/server/rest/services/GCCDepts/EDPMobile2025/FeatureServer/2'


@lru_cache(maxsize=1)
def chennai_ward_boundaries():
    """Fetch official GCC ward boundaries as WGS84 GeoJSON and cache them in-process."""
    params = {
        'where': '1=1',
        'outFields': 'ward,zone,region,ac_name,ward_id,zone_id,gccdept_sde_wardboundary_area',
        'returnGeometry': 'true',
        'outSR': '4326',
        'f': 'geojson',
    }
    try:
        response = httpx.get(GCC_WARD_SERVICE, params=params, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RuntimeError('Official GCC ward boundary service is temporarily unavailable.') from error
    features = [feature for feature in payload.get('features', []) if feature.get('geometry')]
    if not features:
        raise RuntimeError('Official GCC ward boundary service returned no usable features.')
    return {
        'type': 'FeatureCollection',
        'features': features,
        'evidence_type': 'OBSERVED DATA',
        'geography': 'Greater Chennai Corporation wards',
        'period': '2025 service layer',
        'source_org': 'Greater Chennai Corporation',
        'source_url': GCC_WARD_SOURCE,
        'provenance': 'Official GCC GIS FeatureServer. Administrative boundaries and attributes only.',
        'data_boundary': 'The map does not infer ward-level household, water, electricity, amenity, behavioural, or simulation values from the boundary layer.',
    }


def ward_profile(ward_number: str):
    data = chennai_ward_boundaries()
    match = next((feature for feature in data['features'] if str(feature.get('properties', {}).get('ward')) == str(ward_number)), None)
    if not match:
        raise KeyError(ward_number)
    properties = match.get('properties', {})
    return {
        'evidence_type': 'OBSERVED DATA',
        'ward': str(properties.get('ward', ward_number)),
        'zone': properties.get('zone'),
        'region': properties.get('region'),
        'assembly_constituency': properties.get('ac_name'),
        'official_area_square_metres': properties.get('gccdept_sde_wardboundary_area'),
        'source_org': 'Greater Chennai Corporation',
        'source_url': GCC_WARD_SOURCE,
        'provenance': 'Administrative fields returned by the official GCC 2025 ward boundary service.',
        'data_boundary': 'No socioeconomic or behavioural indicator is claimed to be observed for this ward in this profile.',
    }
