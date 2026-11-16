import os
import re
import logging
from typing import Optional
from fastapi import APIRouter, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse
from ..services.tile_service import get_tile_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tiles", tags=["Vector Tiles & PMTiles (VMRDA 2041)"])

# MIME types according to Mapbox Vector Tile Specification
MVT_MIME_TYPE = "application/vnd.mapbox-vector-tile"
PMTILES_MIME_TYPE = "application/octet-stream"

@router.get("/tilejson.json", summary="TileJSON 3.0.0 Specification")
def get_tilejson_spec(request: Request):
    """
    Returns official TileJSON 3.0.0 metadata describing vector tile layers,
    bounding box (7,328 km² VMRDA), zoom levels, and feature attributes.
    """
    base_url = str(request.base_url).rstrip("/")
    tile_service = get_tile_service()
    return JSONResponse(
        content=tile_service.get_tilejson(base_url),
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*"
        }
    )

@router.get("/stats", summary="Vector Tile Engine Statistics")
def get_tile_stats():
    """
    Returns live performance telemetry and spatial indexing metrics
    for the cadastral vector tile engine.
    """
    tile_service = get_tile_service()
    pmtiles_exists = os.path.exists(tile_service.pmtiles_path)
    pmtiles_sz = os.path.getsize(tile_service.pmtiles_path) if pmtiles_exists else 0

    return {
        "status": "healthy",
        "engine": "GeoDueDiligence Spatial Grid Hash Vector Engine",
        "region": "Visakhapatnam Metropolitan Region Development Authority (VMRDA)",
        "jurisdiction_area_km2": 7328,
        "indexed_parcels": len(tile_service.parcels_list),
        "spatial_grid_cells": len(tile_service.spatial_grid),
        "in_memory_cached_tiles": len(tile_service._tile_cache),
        "pmtiles_archive": {
            "path": tile_service.pmtiles_path,
            "exists": pmtiles_exists,
            "size_bytes": pmtiles_sz,
            "size_mb": round(pmtiles_sz / (1024 * 1024), 2),
            "spec_version": 3,
            "min_zoom": 12,
            "max_zoom": 14
        },
        "supported_layers": [
            "all",
            "cadastral_parcels",
            "vmrda_zoning",
            "water_buffers",
            "public.cadastral_parcels",
            "public.vmrda_zoning_2041"
        ],
        "bounds": tile_service.VMRDA_BOUNDS
    }

@router.get("/{layer}/{z}/{x}/{y}.pbf", summary="Mapbox Vector Tile (.pbf)")
@router.get("/public.{layer}/{z}/{x}/{y}.pbf", summary="pg_tileserv Compatible Endpoint")
def get_vector_tile(
    layer: str,
    z: int,
    x: int,
    y: int,
    request: Request
):
    """
    Dynamically serves Mapbox Vector Tiles (.pbf / .mvt) for the requested layer and tile coordinates.
    pg_tileserv drop-in compatible format (e.g. /public.cadastral_parcels/{z}/{x}/{y}.pbf).
    """
    if z < 0 or z > 22 or x < 0 or y < 0:
        raise HTTPException(status_code=400, detail="Invalid tile coordinates")

    tile_service = get_tile_service()
    
    # Strip optional 'public.' prefix if passed in path
    clean_layer = layer.replace("public.", "")

    try:
        mvt_bytes = tile_service.get_tile(clean_layer, z, x, y, compress=False)
    except Exception as e:
        logger.error(f"Tile generation error for {clean_layer}/{z}/{x}/{y}: {e}")
        raise HTTPException(status_code=500, detail="Tile generation failed")

    return Response(
        content=mvt_bytes,
        media_type=MVT_MIME_TYPE,
        headers={
            "Content-Type": MVT_MIME_TYPE,
            "Cache-Control": "public, max-age=86400, stale-while-revalidate=3600",
            "Access-Control-Allow-Origin": "*",
            "X-Tile-Layer": clean_layer,
            "X-Tile-Coord": f"{z}/{x}/{y}",
            "X-Tile-Size-Bytes": str(len(mvt_bytes))
        }
    )

@router.head("/pmtiles/vmrda_parcels.pmtiles", summary="PMTiles Archive HEAD Request")
def pmtiles_head(request: Request):
    """
    Responds to HTTP HEAD requests from PMTiles client libraries to verify
    file presence, content size, and byte-range request capability.
    """
    tile_service = get_tile_service()
    if not os.path.exists(tile_service.pmtiles_path):
        raise HTTPException(status_code=404, detail="PMTiles archive not found. Bake archive first.")

    file_size = os.path.getsize(tile_service.pmtiles_path)
    return Response(
        status_code=status.HTTP_200_OK,
        media_type=PMTILES_MIME_TYPE,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": PMTILES_MIME_TYPE,
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*"
        }
    )

@router.get("/pmtiles/vmrda_parcels.pmtiles", summary="PMTiles Range-Request Endpoint")
def get_pmtiles_archive(request: Request):
    """
    Serves PMTiles archive with full HTTP 206 Partial Content byte-range support.
    Enables sub-second random access to any cadastral tile without loading the full archive into browser memory.
    """
    tile_service = get_tile_service()
    if not os.path.exists(tile_service.pmtiles_path):
        raise HTTPException(status_code=404, detail="PMTiles archive not found. Bake archive first.")

    file_path = tile_service.pmtiles_path
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("Range")

    if not range_header:
        # Full file download request
        return FileResponse(
            path=file_path,
            media_type=PMTILES_MIME_TYPE,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*"
            }
        )

    # Parse Byte-Range: e.g., 'bytes=0-16383' or 'bytes=500-'
    match = re.match(r"bytes=(\d+)-(\d+)?", range_header)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"}
        )

    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1

    if start >= file_size or end >= file_size or start > end:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"}
        )

    length = end - start + 1
    with open(file_path, "rb") as f:
        f.seek(start)
        data = f.read(length)

    return Response(
        content=data,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=PMTILES_MIME_TYPE,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(len(data)),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length"
        }
    )
