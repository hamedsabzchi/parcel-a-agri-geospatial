"""Stage 02 discovery orchestration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from .config import load_dataset_registry, load_project_config, project_path
from .inventory import Inventory
from .metadata import git_commit, package_versions, sha256_file, utc_now
from .reporting import write_coverage_map, write_html_report
from .sources import NetworkClient, create_adapter
from .validation import AOIContext, load_aoi


class DiscoveryRunner:
    """Run source checks independently and write the Stage 02 deliverables."""

    def __init__(
        self,
        project_root: str | Path,
        project_config_path: str | Path = "config/project.yml",
        registry_path: str | Path = "config/datasets.yml",
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.config_path = project_path(self.project_root, project_config_path)
        self.registry_path = project_path(self.project_root, registry_path)
        self.config = load_project_config(self.config_path)
        self.config["project_root"] = str(self.project_root)
        self.registry = load_dataset_registry(self.registry_path)
        self.aoi: AOIContext = load_aoi(
            project_path(self.project_root, self.config["aoi_path"]),
            str(self.config["aoi_identifier"]),
        )
        self.output_dir = project_path(self.project_root, self.config["output_directory"])
        self.cache_dir = project_path(self.project_root, self.config["cache_directory"])
        self.log_dir = self.output_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.logger = self._logger(self.log_dir / "discovery_log.txt")
        self.client = NetworkClient(self.config, self.cache_dir)
        self.inventory = Inventory()
        self.completed: set[str] = set()
        self.progress = progress or print

    @staticmethod
    def _logger(path: Path) -> logging.Logger:
        logger = logging.getLogger(f"parcel_a_stage02_{path}")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.FileHandler(path, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)sZ %(levelname)s %(message)s"))
        logger.addHandler(handler)
        return logger

    def _run_records(self, records: list[dict[str, Any]]) -> None:
        for index, dataset in enumerate(records, start=1):
            dataset_id = str(dataset["dataset_id"])
            if dataset_id in self.completed:
                continue
            self.progress(f"{index}/{len(records)} {dataset_id}")
            self.logger.info("START %s", dataset_id)
            try:
                adapter = create_adapter(
                    dataset,
                    self.config,
                    self.aoi,
                    self.client,
                    self.logger,
                )
                record = adapter.run()
            except Exception as error:
                self.logger.exception("UNHANDLED %s", dataset_id)
                record = {
                    **dataset,
                    "access_status": "VERIFICATION_FAILED",
                    "AOI_coverage_status": "COVERAGE_UNKNOWN",
                    "valid_data_status": "VERIFICATION_FAILED",
                    "failure_reason": f"{type(error).__name__}: {error}",
                    "agricultural_relevance": dataset.get("initial_priority", "SUPPORTING"),
                    "processing_priority": "NEEDS_MANUAL_REVIEW",
                    "recommended_stage": "LATER_OR_REVIEW",
                    "validation_date_utc": utc_now(),
                }
            self.inventory.add(record)
            self.completed.add(dataset_id)
            self.logger.info(
                "END %s coverage=%s valid=%s priority=%s",
                dataset_id,
                record.get("AOI_coverage_status"),
                record.get("valid_data_status"),
                record.get("processing_priority"),
            )

    def run_fao(self) -> None:
        self._run_records([item for item in self.registry if item["source_group"] == "FAO"])

    def run_non_fao(self) -> None:
        self._run_records(
            [item for item in self.registry if item["source_group"] not in {"FAO", "Future climate"}]
        )

    def run_future_climate(self) -> None:
        self._run_records([item for item in self.registry if item["source_group"] == "Future climate"])

    def run_all(self) -> Inventory:
        self._run_records(self.registry)
        return self.inventory

    def write_outputs(self) -> dict[str, Path]:
        table_dir = self.output_dir / "tables"
        metadata_dir = self.output_dir / "metadata"
        map_dir = self.output_dir / "maps"
        paths = self.inventory.write(table_dir, metadata_dir)
        paths["map"] = write_coverage_map(
            self.inventory,
            self.registry,
            self.aoi,
            map_dir / "data_coverage_map.html",
        )
        paths["report"] = write_html_report(
            self.inventory,
            self.aoi,
            self.output_dir / "stage02_report.html",
        )
        paths["log"] = self.log_dir / "discovery_log.txt"
        discovery_time = utc_now()
        reproducibility = {
            "execution_date_utc": discovery_time,
            "data_discovery_date_utc": discovery_time,
            "aoi_checksum_sha256": self.aoi.checksum,
            "configuration_checksum_sha256": sha256_file(self.config_path),
            "registry_checksum_sha256": sha256_file(self.registry_path),
            "notebook_version": self.config.get("notebook_version", "UNKNOWN"),
            "git_commit": git_commit(self.project_root),
            "query_parameters": {
                "aoi_bbox_wgs84": list(self.aoi.bounds),
                "aoi_centroid_wgs84": list(self.aoi.centroid),
                "test_dates": self.config.get("test_dates", "UNKNOWN"),
                "maximum_raster_sample_mb": self.config.get(
                    "maximum_raster_sample_mb", "UNKNOWN"
                ),
                "maximum_vector_features": self.config.get(
                    "maximum_vector_features", "UNKNOWN"
                ),
                "maximum_download_mb": self.config.get("maximum_download_mb", "UNKNOWN"),
            },
            "package_versions": package_versions(
                ["geopandas", "pandas", "requests", "shapely", "pyproj", "PyYAML", "folium"]
            ),
            "summary": self.inventory.summary(),
        }
        run_metadata = metadata_dir / "run_metadata.json"
        run_metadata.write_text(
            json.dumps(reproducibility, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        paths["run_metadata"] = run_metadata
        return paths
