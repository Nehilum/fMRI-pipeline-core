import typer
import yaml
import logging
import sys
import pickle
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler

# Import Phase 1-5 Logic (BIDS Assembler)
from neuro_mod.phase_bids.phases.p01_raw_ingest import get_ingestor
from neuro_mod.phase_bids.phases.p02_raw_conversion import RawConverter
from neuro_mod.phase_bids.phases.p03_1_preaudit import MappingGenerator
from neuro_mod.phase_bids.phases.p03_2_compilation import BidsCompilationStep
from neuro_mod.phase_bids.phases.p04_skeleton import SkeletonCreator
from neuro_mod.phase_bids.phases.p05_assembler import Assembler
from neuro_mod.phase_bids.core.models import ProcessStatus

# Import Phase 6 Logic (fMRIPrep Engine)
from neuro_mod.phase_preproc import fmriprep_cli

app = typer.Typer(pretty_exceptions_show_locals=False)
bids_app = typer.Typer()
fmriprep_app = typer.Typer()

app.add_typer(bids_app, name="bids", help="Phases 1-5: DICOM to BIDS conversion pipeline.")
app.add_typer(fmriprep_app, name="fmriprep", help="Phase 6: fMRIPrep execution and array extraction.")

console = Console()

def setup_logging(log_dir: Path, level=logging.INFO):
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True), logging.FileHandler(log_dir / "pipeline.log")]
    )
    return logging.getLogger("neuro-mod")

def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

class BidsPipelineRunner:
    def __init__(self, config_path: Path):
        self.config_path = str(config_path)
        self.config = load_config(config_path)
        self.work_dir = Path(self.config['paths']['work_dir'])
        self.logger = setup_logging(self.work_dir / "logs")
        self.ckpt_p1 = self.work_dir / "checkpoint_01_ingest.pkl"
        self.ckpt_p2 = self.work_dir / "checkpoint_02_converted.pkl"
        self.entries = []

    def load_checkpoint(self, path: Path):
        if not path.exists(): return False
        with open(path, 'rb') as f:
            self.entries = pickle.load(f)
        return True

    def save_checkpoint(self, path: Path):
        with open(path, 'wb') as f:
            pickle.dump(self.entries, f)

    def run_p1(self):
        self.logger.info("[bold blue]Phase 1:[/bold blue] Raw Ingest")
        ingestor = get_ingestor(self.config)
        self.entries = ingestor.run()
        self.save_checkpoint(self.ckpt_p1)
        return True

    def run_p2(self):
        if not self.entries and not self.load_checkpoint(self.ckpt_p1):
            self.logger.error("Phase 1 results not found. Run Phase 1 first.")
            return False
        self.logger.info("[bold blue]Phase 2:[/bold blue] Raw Conversion")
        converter = RawConverter(self.config)
        converter.execute(self.entries)
        self.save_checkpoint(self.ckpt_p2)
        return True

    def run_p3a(self):
        if not self.entries and not self.load_checkpoint(self.ckpt_p2):
            self.logger.error("Phase 2 results not found. Run Phase 2 first.")
            return False
        self.logger.info("[bold blue]Phase 3.1:[/bold blue] Mapping Generation (Audit)")
        mapper = MappingGenerator(self.config)
        mapper.execute(self.entries)
        return True

    def run_p3b(self):
        self.logger.info("[bold blue]Phase 3.2:[/bold blue] BIDS Compilation")
        compiler = BidsCompilationStep(self.config)
        compiler.execute()
        return True

    def run_p4(self):
        self.logger.info("[bold blue]Phase 4:[/bold blue] Skeleton Creation")
        creator = SkeletonCreator(self.config_path)
        creator.run()
        return True

    def run_p5(self):
        self.logger.info("[bold blue]Phase 5:[/bold blue] Final Assembly")
        assembler = Assembler(self.config_path)
        assembler.run()
        return True

@bids_app.command("prepare")
def bids_prepare(config: Path = typer.Option("configs/config.yaml", help="Path to config.yaml")):
    """Run Phase 1-3.1: Ingest, Convert, and Generate Audit Spreadsheet."""
    runner = BidsPipelineRunner(config)
    if runner.run_p1():
        if runner.run_p2():
            runner.run_p3a()
            console.print("[bold green]Success![/bold green] Please review the generated audit spreadsheet.")

@bids_app.command("build")
def bids_build(config: Path = typer.Option("configs/config.yaml", help="Path to config.yaml")):
    """Run Phase 3.2-5: Compile Mapping and Build BIDS Structure."""
    runner = BidsPipelineRunner(config)
    if runner.run_p3b():
        if runner.run_p4():
            if runner.run_p5():
                console.print("[bold green]BIDS Construction Complete![/bold green]")

@fmriprep_app.command("run")
def fmriprep_run(config: Path = typer.Option("configs/config.yaml"), dry_run: bool = False):
    """Phase 6: Run fMRIPrep container."""
    fmriprep_cli.main(["--config", str(config), "run"] + (["--dry-run"] if dry_run else []))

@fmriprep_app.command("extract")
def fmriprep_extract(config: Path = typer.Option("configs/config.yaml")):
    """Phase 6: Extract (t,x,y,z) arrays from fMRIPrep."""
    fmriprep_cli.main(["--config", str(config), "extract"])

@app.command("init")
def init(project_name: str):
    """Initialize a new fMRI project directory structure."""
    base = Path(project_name)
    dirs = ["raw", "sourcedata", "derivatives", "work", "configs", "scripts"]
    for d in dirs:
        (base / d).mkdir(parents=True, exist_ok=True)
    console.print(f"Project [bold cyan]{project_name}[/bold cyan] initialized.")

if __name__ == "__main__":
    app()
