import logging
import os
import signal
import sys

import click
from azure.ai.ml import MLClient
from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContainerClient
from azure.storage.fileshare import ShareDirectoryClient

BLOB_PREFIX = "notebooks_fileshare"

SUBSCRIPTION_ID = os.environ.get(
    "AZURE_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000"
)
RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "test-resource-group")
WORKSPACE_NAME = os.environ.get("AZURE_WORKSPACE_NAME", "test-workspace")

log = logging.getLogger(__name__)


def _signal_handler(sig: int, frame: object) -> None:
    click.echo("\nInterrupted.", err=True)
    sys.exit(130)


signal.signal(signal.SIGINT, _signal_handler)


def _should_copy(name: str, *, notebooks_only: bool) -> bool:
    """Return True if the file should be copied based on the filter mode."""
    if not notebooks_only:
        return True
    return name.endswith(".ipynb")


def sync_directory(
    dir_client: ShareDirectoryClient,
    blob_container: ContainerClient,
    *,
    recursive: bool = True,
    notebooks_only: bool = True,
    path_prefix: str = "",
) -> int:
    """Sync files from an Azure file share directory to blob storage.

    Args:
        dir_client: File share directory client to read from.
        blob_container: Blob container client to write to.
        recursive: Whether to recurse into subdirectories.
        notebooks_only: If True, copy only .ipynb files; otherwise copy everything.
        path_prefix: Path prefix for building blob paths.

    Returns:
        Number of files synced.
    """
    count = 0
    for item in dir_client.list_directories_and_files():
        item_path = f"{path_prefix}/{item['name']}" if path_prefix else item["name"]

        if item["is_directory"]:
            if recursive:
                sub_dir = dir_client.get_subdirectory_client(item["name"])
                count += sync_directory(
                    sub_dir,
                    blob_container,
                    recursive=recursive,
                    notebooks_only=notebooks_only,
                    path_prefix=item_path,
                )
        elif _should_copy(item["name"], notebooks_only=notebooks_only):
            file_client = dir_client.get_file_client(item["name"])
            data = file_client.download_file().readall()
            blob_path = f"{BLOB_PREFIX}/{item_path}"
            blob_container.upload_blob(blob_path, data, overwrite=True)
            log.info("Synced: %s -> %s", item_path, blob_path)
            click.echo(f"  Synced: {item_path} -> {blob_path}")
            count += 1

    return count


@click.command()
@click.option(
    "--recursive/--no-recursive",
    default=True,
    show_default=True,
    help="Recurse into subdirectories.",
)
@click.option(
    "--notebooks-only/--all-files",
    default=True,
    show_default=True,
    help="Copy only .ipynb files, or copy everything.",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.version_option(version="0.1.0")
def cli(
    recursive: bool,
    notebooks_only: bool,
    verbose: bool,
) -> None:
    r"""Sync notebooks from an AzureML file share to blob storage.

    Reads from the workspace working directory file share and uploads
    to the workspace blob store under the notebooks_fileshare/ prefix.

    Requires environment variables:
      AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_WORKSPACE_NAME

    \b
    Examples:
      sync_notebooks
      sync_notebooks --no-recursive --all-files
      sync_notebooks --verbose
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    credential = DefaultAzureCredential()

    try:
        ml_client = MLClient(
            credential,
            subscription_id=SUBSCRIPTION_ID,
            resource_group_name=RESOURCE_GROUP,
            workspace_name=WORKSPACE_NAME,
        )

        file_ds = ml_client.datastores.get("workspaceworkingdirectory")
        blob_ds = ml_client.datastores.get("workspaceblobstore")
    except HttpResponseError as exc:
        click.secho(f"Error connecting to AzureML: {exc.message}", fg="red", err=True)
        sys.exit(1)

    mode = "notebooks only" if notebooks_only else "all files"
    depth = "recursive" if recursive else "top-level only"
    click.echo(f"Source:  {file_ds.account_name}/{file_ds.file_share_name}")
    click.echo(f"Dest:    {blob_ds.account_name}/{blob_ds.container_name}")
    click.echo(f"Mode:    {mode}, {depth}")

    share_dir = ShareDirectoryClient(
        account_url=f"https://{file_ds.account_name}.file.core.windows.net",
        share_name=file_ds.file_share_name,
        directory_path="",
        credential=credential,
        token_intent="backup",
    )

    blob_service = BlobServiceClient(
        account_url=f"https://{blob_ds.account_name}.blob.core.windows.net",
        credential=credential,
    )
    blob_container = blob_service.get_container_client(blob_ds.container_name)

    try:
        total = sync_directory(
            share_dir,
            blob_container,
            recursive=recursive,
            notebooks_only=notebooks_only,
        )
    except HttpResponseError as exc:
        click.secho(f"Error during sync: {exc.message}", fg="red", err=True)
        sys.exit(1)

    click.secho(
        f"\nDone. Synced {total} file(s) to {blob_ds.container_name}/{BLOB_PREFIX}/",
        fg="green",
    )


if __name__ == "__main__":
    cli()
