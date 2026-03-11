import ast
import boto3
import logging
import os

LOG_FILE_NAME = 'ec2-output.log'

class EC2ResourceHandler:
    """EC2 Resource handler."""

    def __init__(self):
        self.client = boto3.client('ec2')

        logging.basicConfig(filename=LOG_FILE_NAME,
                            level=logging.DEBUG, filemode='w',
                            format='%(asctime)s %(message)s',
                            datefmt='%m/%d/%Y %I:%M:%S %p')
        self.logger = logging.getLogger("EC2ResourceHandler")


    # 1. Update the code to search for Amazon Linux AMI ID
    def _get_ami_id(self):
        try: 
            self.logger.info("Retrieving AMI id")
            images_response = self.client.describe_images(
                Owners=['amazon'],
                Filters=[{'Name': 'architecture',
                        'Values': ['x86_64']},
                        {'Name': 'hypervisor',
                        'Values': ['xen']},
                        {'Name': 'virtualization-type',
                        'Values': ['hvm']},
                        {'Name': 'image-type',
                        'Values': ['machine']},
                        {'Name': 'root-device-type',
                        'Values': ['ebs']}
                        ],
            )
            ami_id = ''
            images = images_response['Images']
            for image in images:
                if 'Name' in image:
                    image_name = image['Name']
                    # Modify following line to search for Amazon Linux AMI for us-west-2
                    if image_name.find("amzn2-ami-hvm-") >= 0: #filters for images that have the specific information
                        ami_id = image['ImageId']
                        break
            return ami_id
        except Exception as e: 
            print(e)
            raise e
    
    def _get_userdata(self):
        user_data = """
            #!/bin/bash
            yum update -y
            yum install -y httpd php
            service httpd start
            chkconfig httpd on
            groupadd www
            usermod -a -G www ec2-user
            chown -R root:www /var/www
            chmod 2775 /var/www
            find /var/www -type d -exec chmod 2775 {} +
            find /var/www -type f -exec chmod 0664 {} +
            echo "<?php phpinfo(); ?>" > /var/www/html/phpinfo.php
        """
        return user_data
    
    def _get_security_groups(self):
        security_groups = []
        try: 
            # 2. Get security group id of the 'default' security group
            response = self.client.describe_security_groups(
                Filters=[{'Name': 'group-name', 'Values': ['default']}] #get the id of default 
            )
            default_security_group_id = response['SecurityGroups'][0]['GroupId']

            # 3. Create a new security group
            response = self.client.create_security_group(
                GroupName= 'new-security-group', 
                Description= 'Created new security group to store user data'
            )
            # 4. Authorize ingress traffic for the group from anywhere to Port 80 for HTTP traffic
            http_security_group_id = response['GroupId']

            self.client.authorize_security_group_ingress(
                GroupId=http_security_group_id, 
                IpPermissions=[
                { 
                    'IpProtocol': 'tcp', #for port 80 
                    'FromPort': 80, #allow from port 80 
                    'ToPort': 80,#allow from port 80 
                    'IpRanges': [
                        {'Description': 'SSH access from anywhere', 
                        'CidrIp': '0.0.0.0/0'}
                    ] #traffic can be from anywhere (based on documentation)
                }
                ]
            )

            security_groups.append(default_security_group_id)
            security_groups.append(http_security_group_id)
            return security_groups
        except Exception as e: 
            print(e)
            raise e

    def create(self):
        try: 
            ami_id = self._get_ami_id()
            # print("AMI ID: ", ami_id)

            if not ami_id:
                print("AMI ID missing..Exiting")
                exit()

            user_data = self._get_userdata()

            security_groups = self._get_security_groups()

            response = self.client.run_instances(
                ImageId=ami_id,
                InstanceType='t3.micro', #Had to change to t3 to fix error (checked on Ed)
                MaxCount=1,
                MinCount=1,
                Monitoring={'Enabled': False},
                UserData=user_data,
                SecurityGroupIds=security_groups
            )
            
            # 5. Parse instance_id from the response
            instance_id = response['Instances'][0]['InstanceId'] #get the instanceId
            # print(instance_id)
            return instance_id
        except Exception as e: 
            print(e)
            raise e


    # 6. Add logic to get information about the created instance
    def get(self, instance_id):
        try: 
            self.logger.info("Entered get")

            # Use describe_instances call
            response = self.client.describe_instances( 
                InstanceIds=[instance_id] #get instances
            )


            publicDNS = response['Reservations'][0]['Instances'][0].get("PublicDnsName")
            publicIP = response['Reservations'][0]['Instances'][0].get("PublicIpAddress")

            # print("PublicDNS: ", publicDNS)
            # print("PublicIP", publicIP)

            if publicDNS: 
                print(f"http://{publicDNS}/phpinfo.php")
            if publicIP: 
                print(f"{publicIP}/phpinfo.php")
            return
        except Exception as e: 
            print(e)
            raise e


    # 7. Add logic to terminate the created instance
    def delete(self, instance_id):
        try: 
            self.logger.info("Entered delete")

            # Use terminate_instances call 
            self.client.terminate_instances(
                InstanceIds=[instance_id] #must be called as a list (based on documentation)
            )
            print("Instance terminated is started!")
            
            #from Ed #46 - terminate the instance & create waiter!
            waiter = self.client.get_waiter('instance_terminated') #syntax from documentation
            waiter.wait(InstanceIds=[instance_id]) #must be called as a list (based on documentation)

            self.client.delete_security_group(GroupName='new-security-group')
            print("Security group and instance is terminated!")
            return
        except Exception as e: 
            print(e)
            raise e


def main():

    ec2_handler = EC2ResourceHandler()

    print("Spinning up EC2 instance")

    instance_id = ec2_handler.create()
    print("EC2 instance provisioning started")

    input("Hit Enter to continue>")
    ec2_handler.get(instance_id)

    input("Hit Enter to continue>")
    ec2_handler.delete(instance_id)


if __name__ == '__main__':
    main()