from azure.ai.ml import MLClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContainerClient
from azure.storage.fileshare import ShareDirectoryClient

BLOB_PREFIX = "notebooks_fileshare"


def sync_directory(
    dir_client: ShareDirectoryClient,
    blob_container: ContainerClient,
    path_prefix: str = "",
) -> int:
    """Recursively sync .ipynb files from file share to blob storage."""
    count = 0
    for item in dir_client.list_directories_and_files():
        item_path = f"{path_prefix}/{item['name']}" if path_prefix else item["name"]

        if item["is_directory"]:
            sub_dir = dir_client.get_subdirectory_client(item["name"])
            count += sync_directory(sub_dir, blob_container, item_path)
        elif item["name"].endswith(".ipynb"):
            file_client = dir_client.get_file_client(item["name"])
            data = file_client.download_file().readall()
            blob_path = f"{BLOB_PREFIX}/{item_path}"
            blob_container.upload_blob(blob_path, data, overwrite=True)
            print(f"  Synced: {item_path} -> {blob_path}")
            count += 1

    return count


def main() -> None:
    """Sync notebooks from AzureML file share to blob storage."""
    credential = DefaultAzureCredential()
    ml_client = MLClient(
        credential,
        subscription_id="6535fca9-4fa4-43ee-9320-b2f34de09589",
        resource_group_name="sandbox-rg",
        workspace_name="test-workspace",
    )

    file_ds = ml_client.datastores.get("workspaceworkingdirectory")
    blob_ds = ml_client.datastores.get("workspaceblobstore")

    print(f"Source:  {file_ds.account_name}/{file_ds.file_share_name}")
    print(f"Dest:    {blob_ds.account_name}/{blob_ds.container_name}")

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

    total = sync_directory(share_dir, blob_container)
    print(f"\nDone. Synced {total} notebook(s) to {blob_ds.container_name}/{BLOB_PREFIX}/")


if __name__ == "__main__":
    main()
