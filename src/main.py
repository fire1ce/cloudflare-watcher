import CloudFlare
import smtplib
import logging
import logging.config
import yaml
from deepdiff import DeepDiff
from time import sleep
from os import environ

# Create logger and load logger config file
logger = logging.getLogger("root")
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


### Schedule ###

run_every_x_min = int(environ["RUN_EVERY"])
sleep_for_x_sec = 60 * run_every_x_min

### CloudFlare params ###
cf = CloudFlare.CloudFlare(token=str(environ["CLOUDFLARE_API_TOKEN"]))
cf_domain = str(environ["CLOUDFLARE_DOMAIN"])

# Check if file "cf_records" in data folder exists
def get_referenc_data_from_file(zone_id):
    try:
        with open("data/cf_records_archive_dict", "r") as file:
            cf_records_archive_dict = file.read()
            # Check if file contains dictionary and its not empty
            try:
                if cf_records_archive_dict != "{}":
                    cf_records_archive_dict = eval(cf_records_archive_dict)
                    return cf_records_archive_dict
            except SyntaxError:
                logger.warning("Reference data corapted, recreating it")
    # If file does not exist or empty, create it and return dict as cf_records_archive_dict param
    except FileNotFoundError:
        logger.warning("Reference data does not exist or empty, creating it")
        with open("data/cf_records_archive_dict", "w") as file:
            cf_dns_records = get_cf_records(zone_id)
            cf_records_archive_dict = cf_records_dict(cf_dns_records)
            file.write(str(cf_records_archive_dict))
        return cf_records_archive_dict


# Create a dictionary of the cloudflare A records
def cf_records_dict(cf_dns_records):
    cf_records_dict = {}
    for dns_record in cf_dns_records:
        # Create a dictionary with nested dictionaries for each record content and type
        cf_records_dict[dns_record["name"]] = {
            "content": dns_record["content"],
            "type": dns_record["type"],
        }
    return cf_records_dict


def get_cf_domain_zone_id():
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


# Get cloudflare dns records from cloudflare api
def get_cf_records(zone_id):
    success = False
    try:
        cf_dns_records = cf.zones.dns_records.get(zone_id, params={"per_page": 5000})
        success = True
    except CloudFlare.exceptions.CloudFlareAPIError as error:
        logger.error("Cloudflare api call failed: " + str(error))
    logger.info("Fetched Cloudflare's DNS records successfully for domain: " + cf_domain)
    # return a dict of the cloudflare dns records
    return cf_dns_records, success


# compare the records from cloudflare api with the records from the file
def compare_diff(cf_records_archive_dict, cf_dns_records_dict):
    records_diff = {}
    # get the differences between the two dictionaries
    records_diff = DeepDiff(cf_records_archive_dict, cf_dns_records_dict, ignore_string_case=True, ignore_order=True)
    # if there are differences, return them
    if records_diff != {}:
        return records_diff
    # if there are no differences, return empty dict
    else:
        records_diff = {}
        return records_diff


# for ever record in the compare_diff dict print what new, updated or deleted records
def print_compare_diff(records_diff, cf_records_archive_dict, cf_dns_records_dict):
    if records_diff == {}:
        logger.info("No changes in DNS records")
    else:
        # print new records
        if "dictionary_item_added" in records_diff:
            logger.info("New records were added:")
            for record in records_diff["dictionary_item_added"]:
                key = record.split("['")[1].split("']")[0]
                logger.info(f"{key} : {cf_dns_records_dict[key]['content']} ({cf_dns_records_dict[key]['type']})")

        if "values_changed" in records_diff:
            logger.info("Records were updated:")
            for record in records_diff["values_changed"]:
                key = record.split("['")[1].split("']")[0]
                logger.info(key + " : " + cf_records_archive_dict[key] + " -> " + cf_dns_records_dict[key])

        # print deleted records
        if "dictionary_item_removed" in records_diff:
            logger.info("Records were deleted:")
            for record in records_diff["dictionary_item_removed"]:
                key = record.split("['")[1].split("']")[0]
                logger.info(key + " : " + cf_records_archive_dict[key])

        # update the file with the new records
        with open("data/cf_records_archive_dict", "w") as file:
            file.write(str(cf_dns_records_dict))


### Main function ###
def main():
    logger.info("====== Starting Cloudflare DNS records monitor =====")
    zone_id = ""
    while True:
        cf_records_archive_dict = get_referenc_data_from_file(zone_id)
        if zone_id == "":
            zone_id, success = get_cf_domain_zone_id()
        if not success:
            continue
        cf_dns_records, success = get_cf_records(zone_id)
        if not success:
            continue
        cf_dns_records_dict = cf_records_dict(cf_dns_records)
        records_diff = compare_diff(cf_records_archive_dict, cf_dns_records_dict)
        print_compare_diff(records_diff, cf_records_archive_dict, cf_dns_records_dict)

        logger.info("Sleeping for " + str(run_every_x_min) + " minutes")
        logger.info("----------------------------------------------------")
        sleep(sleep_for_x_sec)


if __name__ == "__main__":
    main()
