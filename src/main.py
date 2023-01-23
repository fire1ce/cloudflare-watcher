import CloudFlare
import yaml
import validators
from deepdiff import DeepDiff
from time import sleep
from logger import createLogger
import json

# Create logger and load logger config file
logger = createLogger()


def cf_api_call(token, endpoint, params=None):
    try:
        cf = CloudFlare.CloudFlare(token=str(token))
        result = cf.zones.get(params=params)
    except CloudFlare.exceptions.CloudFlareAPIError as error:
        logger.error("Cloudflare api call failed: " + str(error))
        return None, error
    except Exception as error:
        logger.error("Cloudflare api call failed: " + str(error))
        return None, error
    return result, None


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
    cf = CloudFlare.CloudFlare(token=str(cf_api_key))
    try:
        zones = cf.zones.get(params={"name": cf_domain, "per_page": 10})
        if len(zones) > 0:
            success = True
    except CloudFlare.exceptions.CloudFlareAPIError as error:
        logger.error("Cloudflare api call failed: " + str(error) + " for domain: " + cf_domain)
        exit(1)
    except Exception as error:
        logger.error("Cloudflare api call failed: " + str(error) + " for domain: " + cf_domain)
        exit(1)
    return success


# Check if file "records_reference" in data folder exists
def get_referenc_data():
    try:
        with open("data/records_reference.json", "r") as file:
            records_reference = file.read()
            # Check if file contains dictionary and its not empty
            try:
                records_reference = json.loads(records_reference)
                if records_reference == {}:
                    raise SyntaxError
                return records_reference
            except SyntaxError:
                logger.warning("Reference data corrupted, recreating it")
    # If file does not exist or empty, create it and return dict as records_reference param
    except FileNotFoundError:
        logger.warning("Reference data does not exist or empty")
        records_reference = create_reference_data()
        return records_reference


def create_reference_data(cf_domains_zone_ids):
    logger.info("====== Creating reference data ======")
    with open("data/records_reference.json", "w") as file:
        cf_dns_records = get_cf_records(cf_domains_zone_ids)
        records_reference = cf_records_dict(cf_dns_records)
        json.dump(records_reference, file, indent=2)
        logger.info("Reference data created successfully")
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
    return cf_dns_records


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

        # update the file with the new records
        with open("data/records_reference.json", "w") as file:
            file.write(str(cf_dns_records_dict))


### Main function ###
def main():
    cf_domains_zone_ids = get_cf_domains_zone_ids(cf_domains)
    if persist:
        records_reference = get_referenc_data()
    else:
        records_reference = create_reference_data(cf_domains_zone_ids)
    logger.info("====== Starting Cloudflare DNS records monitor =====")

    while True:
        cf_dns_records = get_cf_records(cf_domains_zone_ids)
        cf_dns_records_dict = cf_records_dict(cf_dns_records)
        records_diff = compare_diff(records_reference, cf_dns_records_dict)
        print_compare_diff(records_diff, records_reference, cf_dns_records_dict)
        logger.info("Sleeping for " + str(run_every_x_min) + " minutes")
        logger.info("----------------------------------------------------")
        sleep(sleep_for_x_sec)
        records_reference = get_referenc_data()


if __name__ == "__main__":
    main()
