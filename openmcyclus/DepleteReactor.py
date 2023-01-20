from cyclus.agents import Facility 
from cyclus import lib
import cyclus.typesystem as ts

class DepleteReactor(Facility):
    '''
    Reactor facility that performs depletion of the materials
    in it's inventory using the IndependentOperator in 
    OpenMC.
    '''

    fuel_incommods = ts.VectorString(
        doc="Fresh fuel commodity",
        tooltip="Name of commodity requested",
        uilabel="Input Commodity",
        #uitype="incommodity",
    )

    fuel_inrecipes = ts.VectorString(
        doc = "Fresh fuel recipe",
        tooltip = "Fresh fuel recipe",
        uilabel = "Input commodity recipe"
    )

    fuel_outcommods = ts.VectorString(
        doc="Spent fuel commodity",
        tooltip="Name of commodity to bid away",
        uilabel="Output Commodity",
        uitype="outcommodity",
    )

    fuel_outrecipes = ts.VectorString(
        doc = "Spent fuel recipe",
        tooltip = "Spent fuel recipe",
        uilabel = "Output commodity recipe"
    )

    assem_size = ts.Double(
        doc = "Mass (kg) of a single fuel assembly",
        tooltip="Mass (kg) of a single fuel assembly",
        uilabel="Assembly Size",
        #uitype='assemsize',
        units="kg",
        default= 0
    )

    cycle_time = ts.Double( # perhaps should be int
        doc="Amount of time between requests for new fuel",
        tooltip = "Amount of time between requests for new fuel",
        uilabel="Cycle Time",
        #uitype="cycletime",
        units="months",
        default=0
    )

    refuel_time = ts.Int(
        doc = "Time steps for refueling",
        tooltip="Time steps for refueling",
        uilabel="refueltime",
        default = 0
    )

    n_assem_core = ts.Int(
        doc = "Number of assemblies in a core",
        tooltip = "Number of assemblies in a core",
        uilabel = "n_assem_core",
        default=0
    )

    n_assem_batch = ts.Int( 
        doc = "Number of assemblies per batch",
        tooltip = "Number of assemblies per batch",
        uilabel = "n_assem_batch",
        default=0
    )

    power_cap = ts.Double(
        doc = "Maximum amount of power (MWe) produced",
        tooltip = "Maximum amount of power (MWe) produced",
        uilabel = "power_cap",
        units = "MW",
        default=0
    )
    
    core = ts.ResBufMaterialInv()
    waste = ts.ResBufMaterialInv()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entry_times = []
        self.n_assem_fresh = 0
        self.n_assem_spent = 0
        self.on_for = 0
        self.power_name = "power"
        self.discharged = False

    def tick(self):
        if (self.check_core_full() and self.on_for == self.cycle_time):
            # it's time to reload
            # push batch number of assemblies from CORE to WASTE
            popped = self.core.pop_n(self.n_assem_batch)
            # [todo] calculate burnup / flux spectrum for depletion calculation
            # [todo] do depletion
            # popped = self.deplete(popped)
            self.waste.push(popped)
            # make sure the ones being popped and pushed are the depleted ones
            self.on_for = 0
            self.refueling_for = 1
                
        # finished_cycle = self.context.time - self.cycle_time*self.n_assem_core
        # while (not self.core.empty()) and (self.entry_times[0] > finished_cycle): 
        #     self.waste.push(self.core.pop(self.assem_size))
        #     del self.entry_times[0]
        print("tick ",self.context.time, "core:", self.core.count, ' waste:', self.waste.count) 

    def tock(self):
        # t = self.context.time
        # finished_cycle = t - self.cycle_time*self.n_assem_core
        print("tock ",self.context.time, "core:", self.core.count, ' waste:', self.waste.count) 
        if (self.cycle_step >=0) and (self.check_core_full()):
            self.produce_power(True)
            self.on_for += 1
        else:
            self.produce_power(False)

    def enter_notify(self):
        super().enter_notify()
        t = self.context.time
        self.core.capacity = self.assem_size*self.n_assem_core
        self.cycle_step = 0
  
    def check_decommission_condition(self):
        super().check_decommission_condition()
        
    def get_material_requests(self): # phase 1
        '''
        Send out bid for fuel_incommods
        '''
        port = []
        qty = {}
        mat = {}
        t = self.context.time
        commods = []
        # if self.check_core_full():
        #     return port
        lack = self.core.capacity - self.core.quantity 
        if lack == 0:
            return port
        n_requests = lack // self.assem_size # number of assemblies to request
        for r in n_requests:
            for commod in self.fuel_commods:
                recipe = self.context.get_recipe(recipes)
                target = ts.Material.create_untracked(self.assem_size, recipe)
                commods = {coomod:target}
                port.append({"commodities":commods, "constraints":request_qty})
                # some sort of preference thing
        # making len(self.fuel_commods) * n_requests ports
            
        #  Initial core laoding (need to fill to capacity)
        # request_qty = self.assem_size # 10
        # for recipes in self.fuel_inrecipes:
        #     recipe = self.context.get_recipe(recipes)
        #     target = ts.Material.create_untracked(request_qty, recipe)
        #     for commod in self.fuel_incommods:
        #         commods = {commod:target}
        #         port.append({"commodities":commods, "constraints":request_qty})
        return port

    def get_material_bids(self, requests): # phase 2
        '''
        Read bids for fuel_outcommods and return bid protfolio
        '''
        bids = []
        reqs = requests['spent_uox']
        recipe_comp = self.context.get_recipe('spent_uox')
        for req in reqs:
            if self.waste.empty():
                break  
            quantity = min(self.waste.quantity, req.target.quantity)
            mat = ts.Material.create_untracked(quantity, recipe_comp)
            bids.append({'request':req, 'offer':mat})
        if len(bids) == 0:
            return 
        port = {"bids": bids, "constraints":self.waste.quantity}
        return port

    def get_material_trades(self, trades): #phase 5.1
        '''
        Trade away material in the waste material buffer
        '''
        responses = {}
        for trade in trades:
            if trade.request.commodity in self.fuel_outcommods:
                mat_list = self.waste.pop_n(self.waste.count)
        #    if len(mat_list) > 1:
        #    for mat in mat_list[1:]:
        #        mat_list[0].absorb(mat)
            responses[trade] = mat_list[0]
            mat = ts.Material.create(self, trade.amt, trade.request.target.comp())
        return responses

    def accept_material_trades(self, responses): # phase 5.2
        '''
        Accept bid for fuel_incommods
        '''
        self.verbose_print(5, 'imma accept')
        for key, mat in responses.items():
            if key.request.commodity in self.fuel_incommods:
                self.core.push(mat)


    def produce_power(self, produce=True):
        if produce:
            lib.record_time_series(lib.POWER, self, float(self.power_cap))
        else:
            lib.record_time_series(lib.POWER, self, 0)
            
    def verbose_print(self, vt, s):
        if (self.context.whatever_verbosity_variable >= vt):
            print(s)
    
    def check_core_full(self):
        if self.core.quantity == self.core.capacity:
            return True
        else:
            return False 
