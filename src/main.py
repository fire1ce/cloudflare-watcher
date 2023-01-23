############################
#### Cloudflare Watcher ####
############################

import CloudFlare
import yaml
import validators
from deepdiff import DeepDiff
from time import sleep
from logger import createLogger
import json

# Global variables
records_reference_file_path = "data/records_reference.json"


# Create logger and load logger config file
logger = createLogger()


def cf_api_call(token, endpoint, params=None):
    try:
        cf = CloudFlare.CloudFlare(token=str(token))
        result = cf.zones.get(params=params)
    except CloudFlare.exceptions.CloudFlareAPIError as error:
        logger.error("Cloudflare api call failed: " + str(error))
        return None
    except Exception as error:
        logger.error("Cloudflare api call failed: " + str(error))
        return None
    return result


def get_cf_domains_zone_ids(cf_domains):
    cf_domains_zone_ids = {}
    for domain in cf_domains:
        try:
            zones = cf_api_call(domain["zone-api-key"], "zones", {"name": domain["name"], "per_page": 10})
            if zones is None or len(zones) == 0:
                raise ValueError("No zones found for domain: " + domain["name"])
            # Use list comprehension to extract the zone ids
            zone_ids = [zone["id"] for zone in zones]
            cf_domains_zone_ids[domain["name"]] = zone_ids[0]
        except ValueError as error:
            logger.error(str(error))
        except Exception as error:
            logger.error("Unexpected error: " + str(error))
    return cf_domains_zone_ids


# Check if api key is valid without zone id
def check_cf_api_key(cf_domain, cf_api_key):
    success = False
    try:
        zones = cf_api_call(cf_api_key, "zones", {"name": cf_domain, "per_page": 10})
        if len(zones) > 0:
            success = True
    except CloudFlare.exceptions.CloudFlareAPIError as error:
        logger.error("Cloudflare api call failed: " + str(error) + " for domain: " + cf_domain)
        exit(1)
    except Exception as error:
        logger.error("Cloudflare api call failed: " + str(error) + " for domain: " + cf_domain)
        exit(1)
    return success


def handle_reference_data_file(records_reference, action):
    try:
        if action == "read":
            with open(records_reference_file_path, "r") as file:
                records_reference = file.read()
                records_reference = json.loads(records_reference)
                return records_reference
        elif action == "write":
            with open(records_reference_file_path, "w") as file:
                try:
                    json.dump(records_reference, file, indent=2)
                except TypeError as error:
                    logger.error("An error occurred while encoding the reference data JSON: " + str(error))
                    return None
        else:
            raise ValueError("Invalid action provided, must be either 'read' or 'write'.")
    except FileNotFoundError:
        logger.warning("Reference data does not exist or empty")
    except json.JSONDecodeError as error:
        logger.error("An error occurred while decoding the reference data JSON: " + str(error))
        return None
    except Exception as error:
        logger.error(
            "An unexpected error occurred while trying to handle file "
            + records_reference_file_path
            + ": "
            + str(error)
        )
        return None


# Check if file "records_reference" in data folder exists
def get_referenc_data_from_file(cf_domains_zone_ids):
    records_reference = handle_reference_data_file(None, "read")
    if records_reference is None:
        logger.warning("Reference data corrupted, recreating it")
        records_reference = get_reference_data(cf_domains_zone_ids)
        handle_reference_data_file(records_reference, "write")
    return records_reference


def get_reference_data(cf_domains_zone_ids):
    logger.info("=> Creating reference data")
    records_reference = get_cf_records(cf_domains_zone_ids)
    logger.info("=> Reference data created successfully")
    return records_reference


# Validate config file and load it
try:
    with open("data/config.yaml", "r") as stream:
        config = yaml.safe_load(stream or {})
    # Check if config file contains all required params
    if "run-every-x-min" not in config or "domains" not in config:
        logger.error("Config file data/config.yaml does not contain all required params")
        exit(1)
    run_every_x_min = config["run-every-x-min"]
    if not isinstance(run_every_x_min, int):
        logger.error("Config file data/config.yaml param run-every-x-min is not integer")
        exit(1)
    # check if persist is present and is boolean value if not print error and exit
    if "persist" not in config or not isinstance(config["persist"], bool):
        logger.error("Config file data/config.yaml param persist is not boolean")
        exit(1)
    persist = config["persist"]
    # check if cf_domains contains at least one domain
    cf_domains = config["domains"]
    if len(cf_domains) == 0:
        logger.error("No domains found in config file data/config.yaml. Please add at least one domain")
        exit(1)
    for domain in cf_domains:
        # check if name exists and is not empty and is valid
        if "name" not in domain or domain["name"] == "" or not validators.domain(domain["name"]):
            logger.error("Domain name not found or is not valid: " + domain["name"])
            exit(1)
        # check if zone-api-key is not empty and exists
        if "zone-api-key" not in domain or domain["zone-api-key"] == "":
            logger.error("Zone api key not found for domain: " + domain["name"])
            exit(1)
        # check if zone-api-key is valid
        if not check_cf_api_key(domain["name"], domain["zone-api-key"]):
            logger.error("Zone api key is not valid for domain: " + domain["name"])
            exit(1)
except FileNotFoundError as error:
    logger.error("Error: " + str(error))
    exit(1)

### Schedule ###
sleep_for_x_sec = 60 * run_every_x_min


# Get cloudflare dns records from cloudflare api
def get_cf_records(cf_domains_zone_ids):
    # success = False
    cf_dns_records = {}
    for domain in cf_domains:
        cf = CloudFlare.CloudFlare(token=str(domain["zone-api-key"]))
        cf_domain = str(domain["name"])
        zone_id = cf_domains_zone_ids[cf_domain]
        try:
            cf_dns_records.update({cf_domain: cf.zones.dns_records.get(zone_id, params={"per_page": 5000})})
            logger.info("Fetched Cloudflare's DNS records successfully for domain: " + cf_domain)
            # success = True
        except CloudFlare.exceptions.CloudFlareAPIError as error:
            logger.error("Cloudflare api call failed: " + str(error) + " for domain: " + cf_domain)
    cf_dns_records_dict = cf_records_dict(cf_dns_records)
    return cf_dns_records_dict


# Create a dictionary of the cloudflare A records
def cf_records_dict(cf_dns_records):
    cf_records_dict = {}
    for domain, dns_records in cf_dns_records.items():
        for dns_record in dns_records:
            cf_records_dict[dns_record["name"]] = {
                "content": dns_record["content"],
                "type": dns_record["type"],
            }
    return cf_records_dict


# compare the records from cloudflare api with the records from the file
def compare_diff(records_reference, cf_dns_records_dict):
    records_diff = {}
    # get the differences between the two dictionaries
    records_diff = DeepDiff(records_reference, cf_dns_records_dict, ignore_string_case=True, ignore_order=True)
    # if there are differences, return them
    if records_diff != {}:
        return records_diff
    # if there are no differences, return empty dict
    else:
        records_diff = {}
        return records_diff


# for ever record in the compare_diff dict print what new, updated or deleted records
def print_compare_diff(records_diff, records_reference, cf_dns_records_dict):
    if records_diff == {}:
        logger.info("No changes in DNS records")
    else:
        # print new records
        if "dictionary_item_added" in records_diff:
            logger.info("New records were added:")
            for record in records_diff["dictionary_item_added"]:
                key = record.split("['")[1].split("']")[0]
                logger.info(
                    cf_dns_records_dict[key]["type"]
                    + " record "
                    + key
                    + ":"
                    + cf_dns_records_dict[key]["content"]
                    + " was added"
                )

        if "values_changed" in records_diff:
            logger.info("Records were updated:")
            for record in records_diff["values_changed"]:
                key = record.split("['")[1].split("']")[0]
                logger.info(
                    cf_dns_records_dict[key]["type"]
                    + " record "
                    + key
                    + ":"
                    + records_reference[key]["content"]
                    + " -> "
                    + cf_dns_records_dict[key]["content"]
                )

        # print deleted records
        if "dictionary_item_removed" in records_diff:
            logger.info("Records were deleted:")
            for record in records_diff["dictionary_item_removed"]:
                key = record.split("['")[1].split("']")[0]
                logger.info(
                    records_reference[key]["type"]
                    + " record "
                    + key
                    + ":"
                    + records_reference[key]["content"]
                    + " was deleted"
                )


def update_records_reference_file(records_reference):
    with open(records_reference_file_path, "w") as file:
        json.dump(records_reference, file, indent=2)


### Main function ###
def main():
    cf_domains_zone_ids = get_cf_domains_zone_ids(cf_domains)
    if persist:
        records_reference = get_referenc_data_from_file(cf_domains_zone_ids)
    else:
        records_reference = get_reference_data(cf_domains_zone_ids)
    logger.info("====== Starting Cloudflare DNS records monitor =====")

    while True:
        cf_dns_records_dict = get_cf_records(cf_domains_zone_ids)
        records_diff = compare_diff(records_reference, cf_dns_records_dict)
        print_compare_diff(records_diff, records_reference, cf_dns_records_dict)
        logger.info("Sleeping for " + str(run_every_x_min) + " minutes")
        logger.info("----------------------------------------------------")
        records_reference = cf_dns_records_dict
        if persist:
            handle_reference_data_file(records_reference, "write")
        sleep(sleep_for_x_sec)


if __name__ == "__main__":
    main()
