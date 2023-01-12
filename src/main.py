import CloudFlare
import logging
import logging.config
import yaml
import validators
from deepdiff import DeepDiff
from time import sleep

# Create logger and load logger config file
logger = logging.getLogger("root")
# logger = logging.getLogger(__name__)
try:
    with open("src/logging.yml", "r") as stream:
        config = yaml.load(stream, Loader=yaml.FullLoader)
    logging.config.dictConfig(config)
except FileNotFoundError as error:
    print("Error: " + str(error))
    exit(1)

##################
### logger Use ###
##################

# logger.debug("debug message")
# logger.info("info message")
# logger.warning("warn message")
# logger.error("error message")
# logger.critical("critical message")


def get_cf_domain_zone_id(cf_domain):
    success = False
    # Query for the zone name and expect only one value back
    try:
        zones = cf.zones.get(params={"name": cf_domain, "per_page": 10})
    except CloudFlare.exceptions.CloudFlareAPIError as error:
        logger.error("Cloudflare api call failed: " + str(error))
    except Exception as error:
        logger.error("Cloudflare api call failed: " + str(error))
    if len(zones) == 0:
        logger.error("No zones found for domain: " + cf_domain)
    # Extract the zone_id which is needed to process that zone
    try:
        zone_id = zones[0]["id"]
        success = True
    except Exception as error:
        logger.error("Could not get zone id: " + str(error))
    return zone_id, success


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


# Get variables from data/config.yaml file
try:
    with open("data/config.yaml", "r") as stream:
        config = yaml.load(stream, Loader=yaml.FullLoader)
    run_every_x_min = config["run-every-x-min"]
    cf_domains = config["domains"]
    # check if cf_domains contains at least one domain
    if len(cf_domains) == 0:
        logger.error("No domains found in config file data/config.yaml. Please add at least one domain")
        exit(1)
    for domain in cf_domains:
        # check if domain-name exists and is not empty and is valid
        if "domain-name" not in domain or domain["domain-name"] == "" or not validators.domain(domain["domain-name"]):
            logger.error("Domain name not found or is not valid: " + domain["domain-name"])
            exit(1)
        # check if zone-api-key is not empty and exists
        if "zone-api-key" not in domain or domain["zone-api-key"] == "":
            logger.error("Zone api key not found for domain: " + domain["domain-name"])
            exit(1)
        # check if zone-api-key is valid
        if not check_cf_api_key(domain["domain-name"], domain["zone-api-key"]):
            exit(1)
        # check if zone-id key exists and is not empty
        if "zone-id" not in domain or domain["zone-id"] == "":
            logger.info(
                "Zone id not found for domain: " + domain["domain-name"] + ". Trying to get it from cloudflare api"
            )
            cf = CloudFlare.CloudFlare(token=str(domain["zone-api-key"]))
            cf_domain = str(domain["domain-name"])
            zone_id, success = get_cf_domain_zone_id(cf_domain)
            if success:
                domain["zone-id"] = zone_id
                # save the zone-id in the config file for future use and avoid api calls to cloudflare
                with open("data/config.yaml", "w") as file:
                    yaml.dump(config, file)
                logger.info(
                    "Zone id found for domain: " + domain["domain-name"] + ": " + zone_id + " and saved in config file"
                )
            else:
                logger.error("Could not get zone id for domain: " + domain["domain-name"] + ". check your api key")
                exit(1)
except FileNotFoundError as error:
    logger.error("Error: " + str(error))
    exit(1)


### Schedule ###
sleep_for_x_sec = 60 * run_every_x_min

# Check if file "records_reference" in data folder exists
def get_referenc_data_from_file():
    try:
        with open("data/records_reference.json", "r") as file:
            records_reference = file.read()
            # Check if file contains dictionary and its not empty
            try:
                if records_reference != "{}":
                    records_reference = eval(records_reference)
                    return records_reference
            except SyntaxError:
                logger.warning("Reference data corapted, recreating it")
    # If file does not exist or empty, create it and return dict as records_reference param
    except FileNotFoundError:
        logger.warning("Reference data does not exist or empty, creating it")
        with open("data/records_reference.json", "w") as file:
            cf_dns_records = get_cf_records()
            records_reference = cf_records_dict(cf_dns_records)
            file.write(str(records_reference))
        return records_reference


# Get cloudflare dns records from cloudflare api
def get_cf_records():
    # success = False
    cf_dns_records = {}
    for domain in cf_domains:
        cf = CloudFlare.CloudFlare(token=str(domain["zone-api-key"]))
        cf_domain = str(domain["domain-name"])
        zone_id = domain["zone-id"]
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
    logger.info("====== Starting Cloudflare DNS records monitor =====")

    while True:
        records_reference = get_referenc_data_from_file()
        cf_dns_records = get_cf_records()
        cf_dns_records_dict = cf_records_dict(cf_dns_records)
        records_diff = compare_diff(records_reference, cf_dns_records_dict)
        print_compare_diff(records_diff, records_reference, cf_dns_records_dict)
        logger.info("Sleeping for " + str(run_every_x_min) + " minutes")
        logger.info("----------------------------------------------------")
        sleep(sleep_for_x_sec)


if __name__ == "__main__":
    main()
