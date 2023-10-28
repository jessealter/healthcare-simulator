#!/usr/bin/env python3
import argparse
import yaml

# Constants
FAMILY_SIZE_MAP = {
    1: "employee_only",
    2: "employee_plus_one",
    3: "family",
}
# Constants for file paths
HEALTHCARE_PLANS_PATH = "examples/healthcare_plans.yml"
SERVICE_PRICES_PATH = "examples/service_prices.yml"
UTILIZATION_PATH = "examples/family_utilization.yml"

def load_yaml_file(file_path):
    print(f"Reading: {file_path}")
    with open(file_path, "r") as f:
        return yaml.safe_load(f)

def read_healthcare_plans(file_path="healthcare_plans.yml"):
    return load_yaml_file(file_path)

def read_service_prices(file_path="service_prices.yml"):
    return load_yaml_file(file_path)


def read_utilization(file_path="family_utilization.yml"):
    return load_yaml_file(file_path)

class CostSharingBalance:
    """
    Class to manage deductibles and out-of-pocket expenses.
    """
    def __init__(self, member_amount, family_amount, per_member, family_size):
        """
        Initialize a CostSharingBalance object to manage deductibles and out-of-pocket expenses.
        
        :param member_amount: The individual member's deductible or out-of-pocket amount.
        :param family_amount: The family's deductible or out-of-pocket amount.
        :param per_member: Boolean indicating if the deductible or out-of-pocket limit is per member.
        """
        # Single person family only needs to meet the individual member amount, regardless of per_member rules
        self.family_amount_original = self.family_amount = family_amount if family_size > 1 else member_amount
        self.member_amount_original = self.member_amount = member_amount
        self.per_member = per_member

    def get_balance(self):
        """
        Get the balance of the deductible or out-of-pocket max.
        
        When the plan rules indicate the balance is tracked per member, we
        return the lesser of the member's balance and the family's balance.
        When either is met, insurance benefits kick in.
        Otherwise, we return the family amount.

        For single person families, we set the family amount to the member amount
        upon initialization, so this doesn't matter.
        """
        if (self.per_member):
            return min(self.member_amount, self.family_amount)
        return self.family_amount
            
    
    def subtract_balance(self, expense):
        """
        Subtract an expense from the deductible or out-of-pocket max balance.

        :param expense: The amount of the expense to subtract from the balance.

        If the plan rules track this balance per-member, then the member's balance
        and family balance are both updated. In a single-person family, the
        per_member flag is irrelevant because no other expenses are processed
        after that person's utilization is processed.
        """
        self.family_amount = max(0, self.family_amount - expense)
        self.member_amount = max(0, self.member_amount - expense)

    def reset_member_balance(self):
        """
        Reset the member's deductible or out-of-pocket max balance.
        """
        self.member_amount = self.member_amount_original

class HealthcarePlan:
    def __init__(
        self,
        name,
        company,
        description,
        network_family,
        contributions,
        HSA_funding,
        cost_sharing,
        out_of_network_coverage,
        plan_deductibles,
        plan_out_of_pocket_max,
        family_size,
    ):
        self.name = name
        self.company = company
        self.description = description
        self.network_family = network_family
        self.contributions = contributions
        self.HSA_funding = HSA_funding
        self.cost_sharing = cost_sharing
        self.out_of_network_coverage = out_of_network_coverage
        self.plan_deductibles = plan_deductibles
        self.plan_out_of_pocket_max = plan_out_of_pocket_max
        self.family_size = family_size
        
        self.deductibles = {}
        self.out_of_pocket_max = {}

        for network_type in ["in_network", "out_of_network"]:
            if plan_deductibles.get(network_type):
                self._init_balances(network_type, plan_deductibles, self.deductibles)
            if plan_out_of_pocket_max.get(network_type):
                self._init_balances(network_type, plan_out_of_pocket_max, self.out_of_pocket_max)

    def _init_balances(self, network_type:str, plan_balances:dict, balances_dict:dict) -> None:
            """
            Initializes the cost sharing balances for a given network type.

            :param network_type: The type of network to initialize the balances for (in_network or out_of_network)
            :type network_type: str
            :param plan_balances: A dictionary containing the member and family amounts for each network type.
            :type plan_balances: dict
            :param balances_dict: A dictionary to store the cost sharing balances for each network type.
            :type balances_dict: dict

            :return: None
            :rtype: None
            """

            balances_dict[network_type] = CostSharingBalance(
                member_amount=plan_balances[network_type]["member"],
                family_amount=plan_balances[network_type]["family"],
                per_member=plan_balances[network_type].get("per_member", False),
                family_size=self.family_size,
            )

    def calculate_total_premium(self, family_size):
        return self.contributions.get(FAMILY_SIZE_MAP.get(family_size, FAMILY_SIZE_MAP[3]))

    def apply_cost_sharing_service(self, network_coverage_level, service_type, service_price, deductible_applies=True):
        """
        Applies cost sharing to a given service price based on the network coverage level and service type.
        This will account for adjustments based on current deductible and out-of-pocket max balances.

        Args:
            network_coverage_level (str): The level of network coverage for the service (e.g. in-network or out-of-network)
            service_type (str): The type of service.
            service_price (float): The price of the service before cost sharing.

        Returns:
            float: The price of the service after cost sharing.
        """
        if network_coverage_level == 'out_of_network' and not self.out_of_network_coverage:
            print("Service type {} is not covered out of network".format(service_type))
            print("Member pays full price: {}".format(service_price))
            return service_price

        # Get the cost-sharing type (e.g. "copay" or "coinsurance") and amount (e.g. 10% or $20)
        try:
            sharing_type, sharing_amount = next(iter(self.cost_sharing[network_coverage_level][service_type].items()))
        except StopIteration:
            print("ERROR: No cost sharing data found for network_coverage_level {}, service_type {}".format(network_coverage_level, service_type))
            return 0
        except KeyError:
            print("No coverage for service type {} at network level {}".format(service_type, network_coverage_level))
            print("Member pays full price: {}".format(service_price))
            # This does not count towards the deductible or out-of-pocket max.
            return service_price

        # Determine the price the member pays if they've met the deductible
        if sharing_type == 'copay':
            cost_after_deductible = sharing_amount
        elif sharing_type == 'coinsurance':
            cost_after_deductible = service_price * (sharing_amount / 100)
        else:
            print("ERROR: Invalid cost sharing type {}".format(sharing_type))
            return 0

        deductible = self.deductibles.get(network_coverage_level, self.deductibles["in_network"])
        out_of_pocket_max = self.out_of_pocket_max.get(network_coverage_level, self.out_of_pocket_max["in_network"])

        return self.__apply_cost_sharing(sharing_type=sharing_type,
            sharing_amount=sharing_amount,
            deductible_applies=deductible_applies,
            cost_before_deductible=service_price,
            cost_after_deductible=cost_after_deductible,
            deductible=deductible,
            out_of_pocket_max=out_of_pocket_max,
        )

    def apply_cost_sharing_prescription(self, rx_name, rx_utilization_details, rx_price, deductible_applies=True):
        """
        Applies cost sharing to a given prescription price based on the type of medication.

        Args:
            rx_name (str): The name of the prescription.
            rx_details (dict): A dictionary containing the type and frequency of the prescription.
            rx_price (float): The price of the prescription before cost sharing.

        Returns:
            float: The price of the prescription after cost sharing.
        """
        tier = rx_utilization_details["type"]

        # Get the cost-sharing type (e.g. "copay" or "coinsurance") and the tiering structure for medications
        # from the plan data.
        sharing_type, tiers = next(iter(self.cost_sharing["in_network"]["prescription_medicine"].items()))
        sharing_amount = tiers[tier]

        # Determine the price the member pays if they've met the deductible
        if sharing_type == 'copay':
            cost_after_deductible = sharing_amount
        elif sharing_type == 'coinsurance':
            cost_after_deductible = rx_price * (sharing_amount / 100)
        else:
            print("ERROR: Invalid cost sharing type {}".format(sharing_type))
            return 0
        
        network_coverage_level = "in_network"   # This simulator currently assumes all medications are in-network
        deductible = self.deductibles.get(network_coverage_level, self.deductibles["in_network"])
        out_of_pocket_max = self.out_of_pocket_max.get(network_coverage_level, self.out_of_pocket_max["in_network"])

        return self.__apply_cost_sharing(
            sharing_type=sharing_type,
            sharing_amount=sharing_amount,
            deductible_applies=deductible_applies,
            cost_before_deductible=rx_price,
            cost_after_deductible=cost_after_deductible,
            deductible=deductible,
            out_of_pocket_max=out_of_pocket_max,
        )
        

    def __apply_cost_sharing(
        self,
        sharing_type: str,
        sharing_amount: float,
        deductible_applies: bool,
        cost_before_deductible: float,
        cost_after_deductible: float,
        deductible: CostSharingBalance,
        out_of_pocket_max: CostSharingBalance,
    ) -> float:
        """
        Applies cost sharing to a given service price based on the network coverage level and service type,
        subtracting from the deductible and out-of-pocket max balances as needed.

        Args:
            deductible: The deductible balance to subtract from.
            out_of_pocket_max: The out-of-pocket max balance to subtract from.
            sharing_type: The type of cost sharing (e.g. copay or coinsurance).
            cost_before_deductible: The cost of the service before the deductible is met.
            cost_after_deductible: The cost of the service after the deductible is met.
            sharing_amount: The amount of the cost sharing (e.g. 10% or $20).

        Returns:
            The cost of the service after cost sharing has been applied.
        """
        # Case: The out-of-pocket max is met, so the member pays nothing
        if out_of_pocket_max.get_balance() <= 0:
            return 0
        
        # Case: The out-of-pocket max is about to be met, so member pays just enough to hit
        # the out_of_pocket_max.
        if out_of_pocket_max.get_balance() <= cost_after_deductible:
            cost = out_of_pocket_max.get_balance()
            out_of_pocket_max.subtract_balance(cost)
            return cost

        # Cases:
        # 1. The out-of-pocket max is not met, but the service is not subject to the deductible OR
        # 2. The out-of-pocket max is not met, but the deductible is met.
        # Member pays coinsurance/copay.
        if deductible.get_balance() <= 0 or not deductible_applies:
            out_of_pocket_max.subtract_balance(cost_after_deductible)
            return cost_after_deductible

        # Case: The deductible is about to be met, so member pays part of the normal
        # cost and the rest is coinsurance/copay.
        if deductible.get_balance() <= cost_before_deductible:
            # Determine how much is owed after paying enugh to meet the deductible
            if sharing_type == "copay":
                # Pay the copay unless the remaining cost of the service is less than the copay
                # (e.g. After paying the last $90 of your deductible towards a $100 service, you
                # would pay the last $10 off instead of paying a $20 copay to cover the $10.)
                # This could potentially be different depending on the plan's specific rules,
                # but the difference is negligible.
                remainder_cost = min(cost_after_deductible, cost_before_deductible - deductible.get_balance())
            else: # coinsurance
                remainder_cost = (cost_before_deductible - deductible.get_balance()) * (sharing_amount / 100)
            cost = deductible.get_balance() + remainder_cost
            deductible.subtract_balance(cost)
            out_of_pocket_max.subtract_balance(cost)
            return cost

        # Case: Neither the out-of-pocket max nor deductible are met (or will be met by this service). 
        # Member pays the full cost.
        deductible.subtract_balance(cost_before_deductible)
        out_of_pocket_max.subtract_balance(cost_before_deductible)
        return cost_before_deductible


def create_healthcare_plans(plan_data, family_size):
    healthcare_plans = {}
    for plan_name, details in plan_data.items():
        # Get the HSA funding amount for the given family size
        if details.get("HSA_funding"):
            family_mapping = FAMILY_SIZE_MAP.get(family_size, FAMILY_SIZE_MAP[3])
            HSA_funding_amount = details["HSA_funding"][family_mapping]
        else:
            HSA_funding_amount = 0
        healthcare_plans[plan_name] = HealthcarePlan(
            name=plan_name,
            company=details["company"],
            description=details["description"],
            network_family=details.get("network_family", "N/A"),
            contributions=details["contributions"],
            HSA_funding=HSA_funding_amount,
            cost_sharing=details["cost_sharing"],
            out_of_network_coverage=details["out_of_network_coverage"],
            plan_deductibles=details["deductibles"],
            plan_out_of_pocket_max=details["out_of_pocket_max"],
            family_size=family_size,
        )
        
    return healthcare_plans

class HealthSim:
    def __init__(self, healthcare_plans, service_prices, utilization):
        self.service_prices = service_prices
        self.utilization = utilization
        self.family_size = len(self.utilization)
        self.healthcare_plans = create_healthcare_plans(healthcare_plans, self.family_size)

    
    def simulate(self):
        simulation_results = {}
        
        for plan_name, plan in self.healthcare_plans.items():
            cost_premium = plan.calculate_total_premium(self.family_size)
            cost_utilization = 0
            for member, member_utilization in self.utilization.items():
                # Reset the member balance for each deductible and out-of-pocket max
                # when we are processing a different member's utilization.
                for deductible in plan.deductibles.values():
                    deductible.reset_member_balance()
                for out_of_pocket in plan.out_of_pocket_max.values():
                    out_of_pocket.reset_member_balance()

                for coverage_level, utilization in member_utilization['service_utilization'].items():
                    if utilization is not None:
                        for service, times in utilization.items():
                            for _ in range(times):
                                member_cost = plan.apply_cost_sharing_service(
                                    network_coverage_level=coverage_level,
                                    service_type=service,
                                    service_price=self.service_prices.get(service, {}).get("cost", 0),
                                    deductible_applies=self.service_prices.get(service, {}).get("deductible_applies", True),
                                )
                                cost_utilization += member_cost

                for rx_name, rx_utilization_details in member_utilization.get('medications', {}).items():
                    for _ in range(rx_utilization_details['frequency']):
                        cost_medication = plan.apply_cost_sharing_prescription(
                            rx_name=rx_name,
                            rx_utilization_details=rx_utilization_details,
                            rx_price = self.service_prices.get('prescription_medicine', {}).get(rx_name, {}).get('cost', 0)
                        )
                        cost_utilization += cost_medication


            # cost_utilization_after_HSA += plan.get_balance_after_HSA()
            # remaining_hsa_balance += plan.get_remaining_HSA_balance()
                            
            simulation_results[plan_name] = {
                "cost_premium": cost_premium,
                "cost_utilization": cost_utilization,
            }
            
            simulation_results[plan_name]["cost_utilization_after_HSA"] = max(cost_utilization - plan.HSA_funding, 0)
            simulation_results[plan_name]["remaining_HSA_balance"] =  max(plan.HSA_funding - cost_utilization, 0)
            simulation_results[plan_name]["total_cost"] = (
                simulation_results[plan_name]["cost_premium"]
                + simulation_results[plan_name]["cost_utilization_after_HSA"]
            )

        return simulation_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcare_plans", "-hp", default=HEALTHCARE_PLANS_PATH, help="Path to healthcare plans YAML file")
    parser.add_argument("--service_prices", "-sp", default=SERVICE_PRICES_PATH, help="Path to service prices YAML file")
    parser.add_argument("--utilization", "-u", default=UTILIZATION_PATH, help="Path to utilization YAML file")
    args = parser.parse_args()

    healthcare_plans_dict = load_yaml_file(args.healthcare_plans)
    service_prices_dict = load_yaml_file(args.service_prices)
    utilization_dict = load_yaml_file(args.utilization)

    sim = HealthSim(healthcare_plans_dict, service_prices_dict, utilization_dict)
    results = sim.simulate()
    print("The results are in!")
    print(yaml.dump(results))

