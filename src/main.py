import CloudFlare
from deepdiff import DeepDiff
from time import sleep
from os import environ


### Schedule ###

run_every_x_min = int(environ["RUN_EVERY"])
sleep_for_x_sec = 60 * run_every_x_min

### CloudFlare params ###
cf = CloudFlare.CloudFlare(token=str(environ["CLOUDFLARE_API_TOKEN"]))
cf_domain = str(environ["CLOUDFLARE_DOMAIN"])

# Check if file "cf_records" in data folder exists
def get_referenc_data_from_file():
    try:
        with open("data/cf_records_archive", "r") as file:
            cf_records_archive = file.read()
            # Check if file contains dictionary and its not empty
            try:
                if cf_records_archive != "{}":
                    cf_records_archive = eval(cf_records_archive)
                    return cf_records_archive
            except SyntaxError:
                print("Reference data is not a dictionary, creating it")
    # If file does not exist or empty, create it and return dict as cf_records_archive param
    except FileNotFoundError:
        print("Reference data does not exist or empty, creating it")
        with open("data/cf_records_archive", "w") as file:
            cf_records_archive = get_cf_records()
            file.write(str(cf_records_archive))
        return cf_records_archive


# Create a dictionary of the cloudflare A records
def cf_records_dict(cf_dns_records):
    cf_records_dict = {}
    for dns_record in cf_dns_records:
        cf_records_dict[dns_record["name"]] = dns_record["content"]
    return cf_records_dict


def get_cf_domain_zone_id():
    print("get_cf_domain_zone_id called")
    # Query for the zone name and expect only one value back
    try:
        zones = cf.zones.get(params={"name": cf_domain, "per_page": 10})
    except CloudFlare.exceptions.CloudFlareAPIError as error:
        print("Cloudflare api call failed: " + str(error))
        exit(1)
    except Exception as error:
        print("Cloudflare api call failed: " + str(error))
        exit(1)
    if len(zones) == 0:
        print("No zones found for domain: " + cf_domain)
        exit(1)
    # Extract the zone_id which is needed to process that zone
    try:
        zone_id = zones[0]["id"]
    except Exception as error:
        print("Could not get zone id: " + str(error))
        exit(1)
    return zone_id


# Get cloudflare dns records from cloudflare api
def get_cf_records():
    try:
        cf_dns_records = cf.zones.dns_records.get(zone_id, params={"per_page": 5000})
    except CloudFlare.exceptions.CloudFlareAPIError as error:
        print("Cloudflare api call failed: " + str(error))
        exit(1)
    print("Fetched Cloudflare's DNS records")
    # return a dict of the cloudflare dns records
    return cf_records_dict(cf_dns_records)


# compare the records from cloudflare api with the records from the file
def compare_diff(cf_records_archive, cf_dns_records):
    records_diff = {}
    # get the differences between the two dictionaries
    records_diff = DeepDiff(cf_records_archive, cf_dns_records, ignore_string_case=True, ignore_order=True)
    # if there are differences, return them
    if records_diff != {}:
        # print("Records diff: " + str(compare_diff))
        return records_diff
    # if there are no differences, return empty dict
    else:
        records_diff = {}
        return records_diff


# for ever record in the compare_diff dict print what new, updated or deleted records
def print_compare_diff(records_diff, cf_records_archive, cf_dns_records):
    if records_diff == {}:
        print("No changes in DNS records")
    else:
        # print new records
        if "dictionary_item_added" in records_diff:
            print("New records:")
            for record in records_diff["dictionary_item_added"]:
                key = record.split("['")[1].split("']")[0]
                print(key + " : " + cf_dns_records[key])
        # print updated records
        if "values_changed" in records_diff:
            print("Updated records:")
            for record in records_diff["values_changed"]:
                key = record.split("['")[1].split("']")[0]
                print(key + " : " + cf_records_archive[key] + " -> " + cf_dns_records[key])

        # print deleted records
        if "dictionary_item_removed" in records_diff:
            print("Deleted records:")
            for record in records_diff["dictionary_item_removed"]:
                key = record.split("['")[1].split("']")[0]
                print(key + " : " + cf_records_archive[key])

        # update the file with the new records
        with open("data/cf_records_archive", "w") as file:
            file.write(str(cf_dns_records))


### Main function ###
if __name__ == "__main__":
    zone_id = ""
    while True:
        cf_records_archive = get_referenc_data_from_file()
        if zone_id == "":
            zone_id = get_cf_domain_zone_id()
        cf_dns_records = get_cf_records()
        records_diff = compare_diff(cf_records_archive, cf_dns_records)
        # print("--------cf_records_archive--------")
        # print(cf_records_archive)
        # print("-------cf_dns_records---------")
        # print(cf_dns_records)
        # print("-------records_diff---------")
        # print(records_diff)
        print_compare_diff(records_diff, cf_records_archive, cf_dns_records)

        print("Sleeping for " + str(run_every_x_min) + " minutes")
        print("----------------------------------------------------")
        sleep(sleep_for_x_sec)
