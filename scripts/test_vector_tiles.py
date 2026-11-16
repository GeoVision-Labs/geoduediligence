"""
Automated Test & Benchmark Suite for Task 6:
Direct PMTiles / Vector Tile Serving (pg_tileserv & static PMTiles) across the 7,328 km² VMRDA Region.
"""

import sys
import os
import time
import json
import urllib.request
import urllib.error
import mapbox_vector_tile
from pmtiles.reader import Reader as PMTilesReader, MemorySource

BASE_URL = "http://127.0.0.1:8000"

def test_tilejson_endpoint():
    print("[TEST 1] TileJSON 3.0.0 Specification Endpoint...")
    url = f"{BASE_URL}/api/v1/tiles/tilejson.json"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        data = json.loads(resp.read().decode("utf-8"))
        
        assert data.get("tilejson") == "3.0.0", "Invalid TileJSON version"
        assert "tiles" in data and len(data["tiles"]) > 0, "Missing tile URL templates"
        assert data.get("minzoom") == 10, "Invalid minzoom"
        assert data.get("maxzoom") == 17, "Invalid maxzoom"
        
        layer_ids = [l["id"] for l in data.get("vector_layers", [])]
        assert "cadastral_parcels" in layer_ids, "Missing cadastral_parcels layer in TileJSON"
        assert "vmrda_zoning" in layer_ids, "Missing vmrda_zoning layer in TileJSON"
        assert "water_buffers" in layer_ids, "Missing water_buffers layer in TileJSON"
        
        print(f"  --> PASSED: TileJSON 3.0.0 valid with layers {layer_ids}")

def test_tile_stats_endpoint():
    print("[TEST 2] Vector Tile Engine Diagnostics & Statistics...")
    url = f"{BASE_URL}/api/v1/tiles/stats"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        stats = json.loads(resp.read().decode("utf-8"))
        assert stats["status"] == "healthy"
        assert stats["indexed_parcels"] > 8000, f"Expected >8000 parcels, got {stats['indexed_parcels']}"
        assert stats["spatial_grid_cells"] > 500, f"Expected >500 grid cells, got {stats['spatial_grid_cells']}"
        assert stats["pmtiles_archive"]["exists"] is True, "PMTiles archive missing"
        print(f"  --> PASSED: Indexed {stats['indexed_parcels']} parcels in {stats['spatial_grid_cells']} spatial bins. PMTiles size: {stats['pmtiles_archive']['size_mb']} MB")

def test_dynamic_mvt_serving_and_decoding():
    print("[TEST 3] Dynamic MVT Serving & Protobuf Decoding (Tile 14/11986/7364)...")
    url = f"{BASE_URL}/api/v1/tiles/all/14/11986/7364.pbf"
    t0 = time.time()
    with urllib.request.urlopen(url) as resp:
        dur = (time.time() - t0) * 1000
        assert resp.status == 200
        assert "application/vnd.mapbox-vector-tile" in resp.headers.get("Content-Type", "")
        raw_pbf = resp.read()
        assert len(raw_pbf) > 5000, f"Tile too small: {len(raw_pbf)} bytes"
        
        decoded = mapbox_vector_tile.decode(raw_pbf)
        assert "cadastral_parcels" in decoded, "cadastral_parcels layer missing from decoded MVT"
        parcels = decoded["cadastral_parcels"]["features"]
        assert len(parcels) > 200, f"Expected >200 parcels in Anandapuram tile, got {len(parcels)}"
        
        # Verify parcel properties
        sample = parcels[0]["properties"]
        assert "survey_no" in sample, "Missing survey_no in parcel properties"
        assert "village_name" in sample, "Missing village_name in parcel properties"
        assert "zone_code" in sample, "Missing zone_code in parcel properties"
        print(f"  --> PASSED: Decoded {len(parcels)} parcels in {dur:.2f} ms. Sample Sy No: {sample['survey_no']}, Zone: {sample['zone_code']}")

def test_pg_tileserv_compatibility():
    print("[TEST 4] pg_tileserv Drop-In Compatibility Endpoints...")
    # Test pg_tileserv alias route for public.cadastral_parcels
    url1 = f"{BASE_URL}/api/v1/tiles/public.cadastral_parcels/14/11986/7364.pbf"
    with urllib.request.urlopen(url1) as resp:
        assert resp.status == 200
        decoded = mapbox_vector_tile.decode(resp.read())
        assert "cadastral_parcels" in decoded
        assert "vmrda_zoning" not in decoded, "Layer isolation failed for cadastral_parcels"
    
    # Test pg_tileserv alias route for public.vmrda_zoning_2041
    url2 = f"{BASE_URL}/api/v1/tiles/public.vmrda_zoning_2041/14/11986/7364.pbf"
    with urllib.request.urlopen(url2) as resp:
        assert resp.status == 200
        decoded = mapbox_vector_tile.decode(resp.read())
        assert "vmrda_zoning" in decoded
    
    print("  --> PASSED: Drop-in compatibility confirmed for both public.cadastral_parcels and public.vmrda_zoning_2041")

def test_pmtiles_head_and_range_requests():
    print("[TEST 5] Static PMTiles Archive HTTP 206 Byte-Range Access...")
    pmtiles_url = f"{BASE_URL}/api/v1/tiles/pmtiles/vmrda_parcels.pmtiles"
    
    # 1. HEAD request
    head_req = urllib.request.Request(pmtiles_url, method="HEAD")
    with urllib.request.urlopen(head_req) as resp:
        assert resp.status == 200
        assert resp.headers.get("Accept-Ranges") == "bytes"
        content_len = int(resp.headers.get("Content-Length", 0))
        assert content_len > 1_000_000, f"Expected >1MB PMTiles file, got {content_len}"

    # 2. Byte Range Request: PMTiles Header (bytes 0 to 127)
    range_req = urllib.request.Request(pmtiles_url, headers={"Range": "bytes=0-127"})
    t0 = time.time()
    with urllib.request.urlopen(range_req) as resp:
        dur = (time.time() - t0) * 1000
        assert resp.status == 206, f"Expected 206 Partial Content, got {resp.status}"
        assert resp.headers.get("Content-Range") == f"bytes 0-127/{content_len}"
        header_bytes = resp.read()
        assert len(header_bytes) == 128
        assert header_bytes[:7] == b"PMTiles", "Invalid PMTiles magic bytes"

    # 3. Read PMTiles metadata directory with Reader
    reader_req = urllib.request.Request(pmtiles_url, headers={"Range": f"bytes=0-{min(content_len-1, 65535)}"})
    with urllib.request.urlopen(reader_req) as resp:
        root_data = resp.read()
    
    reader = PMTilesReader(MemorySource(root_data))
    hdr = reader.header()
    assert hdr.get("version") == 3, f"Expected PMTiles spec version 3, got {hdr.get('version')}"
    print(f"  --> PASSED: HTTP 206 Partial Content verified ({dur:.2f} ms). Magic: 'PMTiles', Spec v3, Addressed tiles: {hdr.get('addressed_tiles_count')}")

def test_sub_second_latency_benchmarks():
    print("[TEST 6] Latency Benchmarking (Target: Sub-Second Vector Delivery)...")
    url = f"{BASE_URL}/api/v1/tiles/all/14/11986/7364.pbf"
    
    latencies = []
    for i in range(10):
        t0 = time.perf_counter()
        with urllib.request.urlopen(url) as resp:
            data = resp.read()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)
    
    min_lat = min(latencies)
    avg_lat = sum(latencies) / len(latencies)
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]
    
    print(f"  --> 10 Consecutive Tile Requests:")
    print(f"      Min Latency: {min_lat:.2f} ms")
    print(f"      Avg Latency: {avg_lat:.2f} ms (Target < 20 ms)")
    print(f"      P95 Latency: {p95_lat:.2f} ms (Target < 50 ms)")
    
    assert avg_lat < 50.0, f"Average latency too high: {avg_lat:.2f} ms"
    print("  --> PASSED: Sub-second vector rendering benchmark fulfilled!")

if __name__ == "__main__":
    print("=" * 70)
    print("  VMRDA 2041 CADASTRAL VECTOR TILE & PMTILES TEST SUITE")
    print("=" * 70)
    try:
        test_tilejson_endpoint()
        test_tile_stats_endpoint()
        test_dynamic_mvt_serving_and_decoding()
        test_pg_tileserv_compatibility()
        test_pmtiles_head_and_range_requests()
        test_sub_second_latency_benchmarks()
        print("=" * 70)
        print("  ALL 6/6 VECTOR TILE & PMTILES TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)
        sys.exit(0)
    except AssertionError as e:
        print(f"\n[FAIL] Assertion error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected test exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
