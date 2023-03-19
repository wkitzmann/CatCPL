#!/usr/bin/env python
# coding: utf-8

# **CatCPL v1.0**
# https://github.com/wkitzmann/CatCPL/
# 
# **Author**: Winald R. Kitzmann
# 
# CatCPL is distributed under the GNU General Public License 3.0 (https://www.gnu.org/licenses/gpl-3.0.html). 
# 
# **Main citation** for CatCPL: XX
# 
# The user interface of CatCPL was created using TkDesigner by Parth Jadhav (https://github.com/ParthJadhav/Tkinter-Designer/) licensened under BSD 3-Clause "New" or "Revised" License (see /gui/tkdesigner_license).
# 
# **Disclaimer**:
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# In[37]:


import pyvisa
import zhinst.ziPython
import zhinst.utils
import time
import re
import math
import numpy as np
import threading as th
import collections
import pandas as pd
import tkinter as tk
import os
import statistics
import scipy.special
import queue

import gui.gui_script

#from IPython.core.interactiveshell import InteractiveShell
#InteractiveShell.ast_node_interactivity = "all"


# In[38]:


class ECommError(Exception):
    pass


# In[39]:


class LogObject():
    log_name = ''
    initialized = False
    log_queue = None
    
    def log(self, s: str, error: bool=False, noID: bool=False):
        if s == '':
            ss = ''
        elif noID:
            ss = s
        else:
            ss = '[{}] {}'.format(self.log_name,s)
        print(ss)
        
        if error or ss.lower().find('error') != -1:
            self.show_error_diag(ss)
            
        if not (self.log_queue is None):
            self.log_queue.put(ss)
        
    def log_ask(self, q:str):
        self.log('<< {}'.format(q))
        
    def log_answer(self,s:str):
        self.log('>> {}'.format(s))
        
    def show_error_diag(self, s:str):
        
        def place_central():
            win.attributes("-alpha", 0.0)
            win.update()             
            
            ws = win.winfo_screenwidth() # width of the screen
            hs = win.winfo_screenheight() # height of the screen  
            w = win.winfo_width() # width of window
            h = win.winfo_height() # height of window            
            x = (ws/2) - (w/2)
            y = (hs/2) - (h/2)

            # set window to center of screen
            win.geometry('%dx%d+%d+%d' % (w, h, x, y))     
            win.attributes("-alpha", 1.0)            
        
        win = tk.Toplevel()

        tk.Label(win, text=s, bg='white').pack()
        tk.Button(win, text='OK', command=win.destroy).pack()
        win.resizable(False, False)
        win.attributes('-topmost', 'true')
        win.configure(bg='white')
        
        place_central()
                
    def close(self):
        pass


# In[40]:


class VisaDevice(LogObject):  
    #query with logging
    def log_query(self, q:str) -> str:
        self.log_ask(q)
        s = self.inst.query(q)
        self.log_answer(s)
        return s
    
    #query for debug purposes
    def debug_query(self,q:str):
        self.inst.write(q)
        self.log_ask(q)
        start_time = time.time()
        while time.time()-start_time < self.inst.timeout/1000:
            try:
                self.log_answer(self.inst.read_bytes(1))
            except pyvisa.VisaIOError:
                self.log("Debug query timeout.")
                break
                
    def close(self):
        self.log('Closing connection...')        
        self.inst.close()
        self.log('Connection closed.')
        initialized = False


# In[41]:


class PEM(VisaDevice):
    #---edit for different model/configuration---
    name = 'ASRL3::INSTR'
    model = 'Hinds PEM controller 200 V01'
    
    log_name = 'PEM'
    retardation = 0.25
    
    #correction factor for sin(A*sin(x)) modulation by PEM: 1/(2*BesselJ(1,A)) with A = PEM amplitude = retardation*2*pi
    bessel_corr = 1/(2*scipy.special.jv(1,retardation*2*scipy.pi))
    bessel_corr_lp = 1/(2*scipy.special.jv(2,retardation*2*scipy.pi))
    
    float_acc = 0.025 #accuracy for checking float values like the wavelength when setting amplitude
    
    def initialize(self, rm:pyvisa.ResourceManager, log_queue:queue.Queue) -> bool:
        self.rm = rm
        self.log_queue = log_queue
        try:
            self.inst = self.rm.open_resource(self.name, timeout = 10)
            self.log('Successfully connected to: '+self.name)
            self.inst.write_termination = ';'
            self.inst.read_termination = '\n'
            #self.log_query_delay = 0.3
            self.inst.baud_rate = 250000
            self.inst.timeout = 3000
            if self.check_response():
                self.log("Test successful!")
                self.log("Retardation = {}.".format(self.retardation))
                self.log("Bessel correction factor = {:.4f}.".format(self.bessel_corr))
                initialized = True
                return True
            else:
                self.log("Test failed. Try restarting PC.")                  
                return False
        except Exception as e:
            self.log("Error connecting to: "+self.name+". "+str(e),True)
            return False
      
    def extract_value(self,s:str) -> str:
        return re.search(r'\((.*?)\)',s).group(1)
    
    #Tests if the device is behaving as expected
    def check_response(self) -> bool:
        r1 = self.get_id()
        r2 = self.extract_value(self.set_active(True))
        return (r1 == self.model) and (int(r2) == 1)
    
    #Checks if the return string suggests, that the device followed an order
    #For get queries: Checks if the group string matches
    #For set queries: Checks if the group string matches and if the value matches (within float_acc for floats)
    #In case it does not match, it will retry n-1 times
    #q = query, grp = group string, isSet = is this a set query?
    #value = set value, isFloat = is value a float?, n = max. no. of tries
    def retry_query(self,q:str,grp:str,isSet:bool=False,value=0,isFloat:bool=False,n:int=3) -> str:
        success = False
        i = 0
        s = ''
        while (not success) and (i<3): 
            try:
                i += 1
                s = self.log_query(q)
                r = re.search(r'\[(.*?)\]\((.*?)\)',s)
                if isSet:
                    if isFloat:
                        success = (r.group(1) == grp) and (math.isclose(float(r.group(2)),value,abs_tol=self.float_acc))               
                    else:
                        success = (r.group(1) == grp) and (int(r.group(2) == value))
                else:
                    success = (r.group(1) == grp)
            except pyvisa.VisaIOError as e:
                self.log("{}: {:d}) Error with query {}: {}.".format(self.name,i,q,str(e)),True)
                success = False
        if not success:
            raise ECommError("Error @{}: Error with query {} (tried {:d} times).".format(self.name,q,i),True)
        else:
            return s  
    
    #The set functions all return the value that the PEM returns after processing the command
    def set_active(self,active:bool) -> str:
        return self.retry_query(q=':SYS:PEMO {:d}'.format(int(active==True)),grp='PEMOUT')
    
    def set_idle(self,idle:bool) -> str:
        return self.retry_query(q=':SYS:IDLE {:d}'.format(int(idle==True)),grp='PIDLE')
    
    def get_id_raw(self) -> str:
        return self.retry_query(q='*IDN?',grp='IDN')

    def get_id(self) -> str:
        return self.extract_value(self.get_id_raw())
    
    def get_stable_raw(self) -> str:
        return self.retry_query(q=':MOD:STABLE?',grp='STABLE')
    
    def get_stable(self) -> str:
        return self.extract_value(self.get_stable_raw())
    
    def get_freq_raw(self) -> str:
        return self.retry_query(q=':MOD:FREQ?',grp='FREQUENCY')
    
    def get_freq(self) -> str:
        return self.extract_value(self.get_freq_raw())
      
    def get_amp_raw(self) -> str:
        return self.retry_query(q=':MOD:AMP?',grp='AMP')

    def get_amp(self) -> str:
        return self.extract_value(self.get_amp_raw())    
       
    def set_amp(self,f:float) -> str:
        return self.retry_query(q=':MOD:AMP {:.2f}'.format(f),grp='AMP',isSet=True,value=f,isFloat=True)
        
    def get_amp_range_raw(self) -> str:
        return self.retry_query(q=':MOD:AMPR?',grp='AMPR')
    
    def get_amp_range_low(self) -> str:
        s = get_amp_range_raw()
        return re.search(r'\((.*?),(.*?)\)',s).group(1)
    
    def get_amp_range_high(self) -> str:
        s = get_amp_range_raw()
        return re.search(r'\((.*?),(.*?)\)',s).group(2)
    
    def get_drv_raw(self) -> str:
        return self.retry_query(q=':MOD:DRV?',grp='DRIVE')
    
    def get_drv(self) -> str:
        return self.extract_value(self.get_drv_raw())
    
    def set_drv(self,f:float) -> str:
        return self.retry_query(q=':MOD:DRV {:.2f}'.format(f),grp='DRIVE',isSet=True,value=f,isFloat=True)

    #Sets wavelength and returns current wavelength value
    def set_nm(self,nm:float) -> str:
        return self.extract_value(self.set_amp(nm*self.retardation))        
    
    def get_nm(self,nm:float) -> str:
        return float(self.get_amp())/self.retardation
    
    def get_cp_error_raw(self) -> str:
        return self.retry_query(q=':SYS:CPE?',grp='CPE')
    
    #relative current error (0-2.5)
    def get_current_error(self) -> str:
        s = get_cp_error_raw()
        return re.search(r'\((.*?),(.*?)\)',s).group(1)
    
    #relative phase error (0-1)
    def get_phase_error(self) -> str:
        s = get_cp_error_raw()
        return re.search(r'\((.*?),(.*?)\)',s).group(2)
    
    def get_voltage_info(self) -> str:
        return self.retry_query(q=':SYS:VC?',grp='VC')


# In[42]:


class Mono(VisaDevice):
    #---edit these for different model---
    name = 'ASRL4::INSTR'
    model = 'SP-2-150i'
    serial = '21551915'
    ok = 'ok'    
    
    log_name = 'MON'
    
    #rm = ResourceManager
    def initialize(self,rm:pyvisa.ResourceManager,log_queue:queue.Queue) -> bool:
        self.rm = rm
        self.log_queue = log_queue
        try:
            self.inst = self.rm.open_resource(self.name, timeout = 10)
            self.log('Successfully connected to: '+self.name)
            self.inst.read_termination = '\r\n'
            self.inst.write_termination = '\r'
            self.inst.baud_rate = 9600
            self.inst.timeout = 5000 #ms
        except pyvisa.VisaIOError as e:
            self.log("Error connecting to: "+self.name+", try using a different USB port: "+str(e),True)
            return False
            
        if self.check_response():
            self.log("Test successful!")
            initialized = True
            return True
        else:
            self.log("Test failed. Try restarting PC or connecting via a different USB port.",True)
            return False
            
    #The test runs the same commands twice and checks whether they produce the same results
    def check_response(self) -> bool:
        r1 = self.log_query('MODEL')
        r2 = self.log_query('SERIAL')
        r3 = self.log_query('MODEL')
        r4 = self.log_query('SERIAL')
        self.log("Move to 1000 nm...")
        r5 = self.log_query('1000 GOTO')
        self.log("Move to 0 nm...")
        r6 = self.log_query('0 GOTO')
        return (r1 == r3) and (r2 == r4) and (self.model in r1) and (self.serial in r2) and (self.ok in r5) and (self.ok in r6)       
        
    def retry_query(self,q:str,n:int=3) -> str:
        success = False
        i = 0
        s = ""
        while (not success) and (i < n):
            i += 1
            try:
                s = self.log_query(q)
                success = self.ok in s
            except pyvisa.VisaIOError as e:
                self.log("{:d}) Error with query {} @{}: {}.".format(i,q,self.name,str(e)),True)
                success = False
        if not success:
            raise ECommError("Error @{} with query {} (tried {:d} times).".format(self.name,q,i),True)
        else:
            return s
              
    def get_model(self) -> str:
        return self.retry_query('MODEL')
    
    def get_serial(self) -> str:
        return self.retry_query('SERIAL')
      
    def get_nm(self) -> str:
        return self.retry_query('?NM')
    
    def set_nm(self,nm) -> str:
        return self.retry_query('{:.2f} GOTO'.format(nm))


# In[43]:


#Controls the Zurich Instruments MFLI lock-in amplifier
class MFLI(LogObject):
    sampling_rate = 104.6 #s-1 data transfer rate    
    time_const = 0.00811410938 #s, time constant of the low-pass filter of the lock-in amplifier
    filter_order = 3
    
    #Low and high limit of control voltage for PMT
    pmt_low_limit = 0.0 #V
    pmt_high_limit = 1.1 #V
    
    pmt_volt = 0.0 #V control voltage of the PMT
    signal_range = 3.0 #V, default signal range
    dwell_time = 0.5 #s, default acquisition time per point
    dwell_time_scaling = 1
    data_set_size = np.ceil(dwell_time*sampling_rate) #number of data points per acquisition
    
    dc_phaseoffset = 0.0 #degrees, results in DC phase at +90 or -90 degrees
    #phaseoffset of the demodulators with respect to the PEM reference signal
    #will be loaded from previous measurements and can be calibrated during runtime
    phaseoffset = 158.056 #degrees
    #relative phaseoffset of 2f component vs. 1f component
    rel_lp_phaseoffset = -22 #degrees
    
    bessel_corr = 0.0 #correction factor for the sin(A sin(x)) modulation of the PEM, will be obtained from PEM
    bessel_corr_lp = 0.0 #correction factor for linear component, will be obtained from PEM
    
    #variables necessary for phaseoffset calibration 
    ac_theta_avg = 0.0
    ac_theta_count = 0
    
    sqrt2 = np.sqrt(2)
    
    def __init__(self,ID:str,logname:str,log_queue:queue.Queue):
        self.devID = ID #ID of the device, for example dev3902
        self.devPath = '/'+self.devID+'/'
        self.log_name = logname
        self.log_queue = log_queue
    
    def connect(self) -> bool:
        try:
            #Device Discovery
            d = zhinst.ziPython.ziDiscovery()
            self.props = d.get(d.find(self.devID))

            #Start API Session
            self.daq = zhinst.ziPython.ziDAQServer(self.props['serveraddress'], self.props['serverport'], self.props['apilevel'])
            self.daq.connectDevice(self.devID, self.props['connected'])

            #Issue a warning and return False if the release version of the API used in the session (daq) does not have the same release version as the Data Server (that the API is connected to).
            zhinst.utils.utils.api_server_version_check(self.daq)
            return True
        except Exception as e:
            self.log('Error connecting: {}'.format(str(e)),True)
            return False            
        
    def disconnect(self):
        self.log('Disconnecting...')
        try:
            self.daq.disconnectDevice(self.devID)
        except Exception as e:
            self.log('Error during disconnecting: {}'.format(str(e)),True)
        
    #initialize the api session for data acquisition (daq)
    def setup_for_daq(self,bessel,bessel_lp) -> bool:
        return self.setup_device(True,True,True,True,True,True,False,bessel,bessel_lp)
        
    #initialize the api session for monitoring the oscilloscope (used for signal tuning)
    def setup_for_scope(self) -> bool:
        return self.setup_device(False,False,False,False,False,False,True)    
    
    def setup_device(self,pmt:bool,ch1:bool,ch2:bool,ch3:bool,ch4:bool,daqm:bool,scp:bool,bessel:float=0.0,bessel_lp:float=0.0) -> bool:
        try:
            if pmt:
                self.log('Setting up device...')
                self.log('PMT voltage control...')
                #Set upper and lower limit for PMT control voltage via Aux Out 1 of MFLI
                self.daq.setDouble(self.devPath+'auxouts/0/limitlower', self.pmt_low_limit)
                self.daq.setDouble(self.devPath+'auxouts/0/limitupper', self.pmt_high_limit)
                #Set output of Aux Out 1 to Manual
                self.daq.setInt(self.devPath+'auxouts/0/outputselect', -1)
                self.set_PMT_voltage(0.0,False)
                self.set_input_range(3.0)

            if ch1:
                self.log('Channel 1...')
                #Channel 1 (AC, CPL)
                self.daq.setInt(self.devPath+'demods/0/adcselect', 0)                
                self.daq.setInt(self.devPath+'extrefs/0/enable', 0)
                self.daq.setDouble(self.devPath+'demods/0/phaseshift', self.phaseoffset)
                self.daq.setInt(self.devPath+'demods/0/oscselect', 0)     
                self.daq.setDouble(self.devPath+'sigins/0/scaling', 1)     
                #filter timeconst
                self.daq.setInt(self.devPath+'demods/0/order', self.filter_order)
                self.daq.setDouble(self.devPath+'demods/0/timeconstant', self.time_const)
                #transfer rate
                self.daq.setDouble(self.devPath+'demods/0/rate', self.sampling_rate)   
                self.daq.setInt(self.devPath+'demods/0/enable', 1)

            if ch2:
                self.log('Channel 2...')
                #Channel 2 (ExtRef)
                self.daq.setInt(self.devPath+'demods/1/adcselect', 8)
                self.daq.setInt(self.devPath+'extrefs/0/enable', 1)
                #deactivate data transfer
                self.daq.setInt(self.devPath+'demods/1/enable', 0)

            if ch3:
                self.log('Channel 3...')
                #Channel 3 (DC, 0 Hz)
                self.daq.setInt(self.devPath+'demods/2/adcselect', 0)
                self.daq.setDouble(self.devPath+'oscs/1/freq', 0)
                self.daq.setDouble(self.devPath+'demods/2/phaseshift', self.dc_phaseoffset)
                self.daq.setInt(self.devPath+'demods/2/order', self.filter_order)
                self.daq.setDouble(self.devPath+'demods/2/timeconstant', self.time_const)                
                self.daq.setDouble(self.devPath+'demods/2/rate', self.sampling_rate)
                self.daq.setInt(self.devPath+'demods/2/enable', 1)
                
            if ch4:
                self.log('Channel 4...')
                #Channel 4 (2f, linear polarization)
                self.daq.setInt(self.devPath+'extrefs/1/enable', 0)
                self.daq.setInt(self.devPath+'demods/3/adcselect', 0)
                self.daq.setDouble(self.devPath+'demods/3/phaseshift', self.phaseoffset + self.rel_lp_phaseoffset) 
                self.daq.setInt(self.devPath+'demods/3/oscselect', 0)  
                self.daq.setInt(self.devPath+'demods/3/harmonic', 2)
                self.daq.setDouble(self.devPath+'sigins/0/scaling', 1)     
                #filter timeconst
                self.daq.setInt(self.devPath+'demods/3/order', self.filter_order)
                self.daq.setDouble(self.devPath+'demods/3/timeconstant', self.time_const)
                #transfer rate
                self.daq.setDouble(self.devPath+'demods/3/rate', self.sampling_rate) 
                self.daq.setInt(self.devPath+'demods/3/enable', 1)

            if daqm:
                self.node_paths = [self.devPath+'demods/0/sample',
                                   self.devPath+'demods/2/sample',
                                   self.devPath+'demods/3/sample'] 
                self.bessel_corr = bessel
                self.bessel_corr_lp = bessel_lp

            if scp:
                self.log('Oscilloscope...')
                self.scope = self.daq.scopeModule()
                self.scope.set('averager/weight', 0)
                self.scope.set('averager/restart', 0)
                self.scope.set('mode', 1)
                #set scope sampling rate to 60 MHz
                self.daq.setInt(self.devPath+'scopes/0/time', 0)
                self.daq.setInt(self.devPath+'scopes/0/trigenable', 0)
                self.daq.setInt(self.devPath+'scopes/0/enable', 0)

                self.scope.unsubscribe('*')
                self.scope.subscribe(self.devPath+'scopes/0/wave')
                self.daq.setDouble(self.devPath+'scopes/0/length', 4096)
                self.scope.set('/historylength', 1)
                self.daq.setInt(self.devPath+'scopes/0/enable', 0)
                self.daq.setInt(self.devPath+'scopes/0/channels/0/inputselect', 0)

            # Perform a global synchronisation between the device and the data server:
            # Ensure that the settings have taken effect on the device before issuing
            # the getSample() command.        
            self.daq.sync()
            
            self.log('Setup complete.')
            return True
        except Exception as e:
            self.log('Error in MFLI setup: '+str(e),True)
            return False
        
    def set_PMT_voltage(self,volt:float,autorange:bool=True):
        self.log('')
        self.log('Setting PMT voltage to: {:.3f} V'.format(volt))
        if (volt <= self.pmt_high_limit) and (volt >= self.pmt_low_limit):
            self.daq.setDouble(self.devPath+'auxouts/0/offset', volt)
            self.pmt_volt = volt
            self.daq.sync()
                   
            self.log('Please wait 10 s for stabilization before starting a measurement.')
            if autorange:
                time.sleep(2)
                self.set_input_range(f=0.0,auto=True)
        else:
            self.log("PMT voltage not set because out of range (0.0-1.1 V): "+str(volt)+" V")
   
    def set_input_range(self,f:float,auto:bool=False):
        if auto:
            self.daq.setInt(self.devPath+'sigins/0/autorange', 1)
        else:
            self.daq.setDouble(self.devPath+'sigins/0/range', f)
        self.daq.sync()            
        time.sleep(1.5)
        self.daq.sync()
        self.signal_range = self.daq.getDouble(self.devPath+'sigins/0/range')
        self.log('')
        self.log('Signal range adjusted to {:.3f} V.'.format(self.signal_range)) 
        
    def set_dwell_time(self,t:float):
        self.log('')
        self.log('Setting dwell time to {:.0f} s.'.format(t))
        #Min. dwell time is 1/sampling rate/dwell_time_scaling to collect 1 datapoint per data chunk
        self.dwell_time = max(t, 1/self.sampling_rate) # TODO Adjust polling duration?
        self.data_set_size = np.ceil(self.dwell_time*self.sampling_rate)
        #self.daq_module.set('duration', self.dwell_time)
        #self.daq_module.set('grid/cols', self.data_set_size)
        #self.daq.sync()
        self.log('Dwell time set to {} s = {:.0f} data points.'.format(self.dwell_time,self.data_set_size))        
    
    def set_phaseoffset(self,f:float):
        self.phaseoffset = f
        self.daq.setDouble(self.devPath+'demods/0/phaseshift', self.phaseoffset)
        self.daq.setDouble(self.devPath+'demods/3/phaseshift', self.phaseoffset)    
        self.daq.sync()
        self.log('Phase offset set to {:.3f} deg'.format(self.phaseoffset))
    
    #activate oscilloscope
    def start_scope(self):
        self.scope.set('clearhistory', 1)
        self.scope.execute()
        self.daq.setInt(self.devPath+'scopes/0/enable', 1)
        self.daq.sync()        
    
    #read data from oscilloscope and return max. and avg. signal
    def read_scope(self):
        data = self.scope.read(True)
        
        max_volt = 0.0
        if self.devPath+'scopes/0/wave' in data:
            if 'wave' in data[self.devPath+'scopes/0/wave'][0][0]:
                for chunk in data[self.devPath+'scopes/0/wave'][0][0]['wave']:
                    max_volt = max(max_volt,chunk.max())
                    avg_volt = statistics.mean(chunk)
            else:
                max_volt = float('nan')
                avg_volt = float('nan')
        else:
            max_volt = float('nan')
            avg_volt = float('nan')                    
            
        return [max_volt,avg_volt]
    
    def stop_scope(self):
        self.scope.finish()
        self.daq.setInt(self.devPath+'scopes/0/enable', 0)
        self.daq.sync()              
        
    #deactivate external reference for a certain oscillator. Used for measurements without modulation by PEM
    def set_extref_active(self,osc_index:int,b:bool):
        if b:
            i = 1 #on
        else:
            i = 0 #off
        self.daq.setInt(self.devPath+'extrefs/'+str(osc_index)+'/enable', i)
    
    #reads demodulator data from MFLI and returns calculated glum etc. 
    #This function is run in a separate thread, that can be aborted by ext_abort_flag[0]
    #provided by Controller instance
    def read_data(self,ext_abort_flag:list) -> dict:
        
        # returns the last n elements of an numpy array
        def np_array_tail(arr: np.array, n:int):
            if n == 0:
                return arr[0:0]
            else:
                return arr[-n:]
        
        def subscribe_to_nodes(paths):
            #Subscribe to data streams
            for path in paths:
                self.daq.subscribe(path)  
            #clear buffer
            self.daq.sync()  
            
        # ensures that all nodes send data regardless of whether the values changed or not
        def prepare_nodes(paths):
            for path in paths:
                self.daq.getAsEvent(path)
        
        # collects data chunks from MFLI using the low-level poll() command and aligns the channels according to their timestamps
        def poll_data(paths) -> np.array:  
            poll_time_step = min(0.1, self.dwell_time*1.3)
        
            # initialize array for raw data
            raw_xy = [[[],[],[]],[[],[],[]],[[],[],[]]] # array_x = sample (0, 2, 3), array_y = timestep, x, y
            filtered_xy = [[[],[]],[[],[]],[[],[]]] # array_x = sample, array_y = x, y            
                                      
            data_count = 0
            data_per_step = poll_time_step * self.sampling_rate        
            expected_poll_count = np.ceil(self.data_set_size/data_per_step)           
            
            # start data buffering
            subscribe_to_nodes(paths)
            
            i = 0
            while (data_count < self.data_set_size) and not ext_abort_flag[0] and (i < expected_poll_count+10):
                prepare_nodes(paths)
                # collects data for poll_time_step
                data_chunk = self.daq.poll(poll_time_step, 100, 0, True)
                
                if is_data_complete(data_chunk, self.node_paths):                
                    # add new data to raw_xy
                    for j in range(0,3):
                        raw_xy[j][0].extend(data_chunk[self.node_paths[j]]['timestamp'])
                        raw_xy[j][1].extend(data_chunk[self.node_paths[j]]['x'])
                        raw_xy[j][2].extend(data_chunk[self.node_paths[j]]['y'])
                
                # find overlap of timestamps between the three samples
                last_overlap = np.intersect1d(np.intersect1d(np.array(raw_xy[0][0]),np.array(raw_xy[1][0])),np.array(raw_xy[2][0]))
                data_count = last_overlap.size
                
                # if only a few values are missing, reduce the poll time accordingly
                if self.data_set_size-data_count < data_per_step:
                    poll_time_step = max(math.ceil((self.data_set_size-data_count)/self.sampling_rate * 1.2), 0.025)
                
                i += 1
            # Stop data buffering
            self.daq.unsubscribe('*')
            
            # identify the timestamps that are identical in all three samples, reduce number of data points to data_set_size (to avoid different numbers of data points at different wavelenghts)
            overlap_timestamps = np_array_tail(last_overlap, int(self.data_set_size))
            
            # filter the x and y data according to overlapping timestamps
            for k in range(0,3):
                # create a list of bools that marks whether a timestamp is in a sample data set or not
                overlap_bools = np.isin(np.array(raw_xy[k][0]), overlap_timestamps)
                # save the filtered x and y data in filtered_xy
                filtered_xy[k][0] = np.array(raw_xy[k][1])[overlap_bools]
                filtered_xy[k][1] = np.array(raw_xy[k][2])[overlap_bools]
            
            return np.array(filtered_xy)
 
        
        def get_sign(theta):
            if np.isnan(theta):
                return 0
            else:
                return np.sign(theta)            
        
        def is_data_complete(chunk, paths) -> bool:
            result = True
            for path in paths:
                result = result and path in chunk
            
            return result
        
        # calculate amplitude R from X and Y
        def get_r(xy: np.array) -> np.array:
            return np.sqrt(xy[0]**2 + xy[1]**2)
        
        # calculate phase theta from X and Y
        def get_theta(xy: np.array) -> np.array:
            return np.arctan2(xy[1], xy[0])    
        
        # generate a filter array of bools that filters out NaN values, False = NaN-value at this index
        def get_nan_filter(raw: np.array) -> np.array:
            nan = [True for _ in range(0, raw[0,0].shape[0])]
            for a in range(0, raw.shape[0]):
                for b in range(0, raw.shape[1]):
                    nan = np.logical_and(nan, np.logical_not(np.isnan(raw[a,b])))
            return nan
        
        # applies the NaN filter to the individual data 
        def apply_nan_filter(raw: np.array, nan: np.array) -> np.array:
            for a in range(0, raw.shape[0]):
                for b in range(0, raw.shape[1]):
                    raw[a,b] = raw[a,b][nan]
            return raw
           
        
        self.log('Starting data aquisition. ({} s)'.format(self.dwell_time))
        error = False        
        
        # Format raw_data: array_x: AC, DC, LP, array_y: x, y
        raw_data = poll_data(self.node_paths)   
        no_data = len(raw_data[0][0]) == 0
        
        if not no_data:
            nan_filter = get_nan_filter(raw_data)
            all_nan = not nan_filter.any()
            
            if not all_nan:
                raw_data = apply_nan_filter(raw_data, nan_filter)

                ac_raw = get_r(raw_data[0])
                ac_theta = get_theta(raw_data[0])

                dc_raw = get_r(raw_data[1])
                dc_theta = get_theta(raw_data[1])

                lp_raw = get_r(raw_data[2])
                lp_theta = get_theta(raw_data[2])  

                sgn = np.vectorize(get_sign)

                # apply sign, correct raw values (Vrms->Vpk) and Bessel correction for AC
                ac = np.multiply(ac_raw, sgn(ac_theta)) * self.sqrt2 * self.bessel_corr
                # sign and lock-in amplifier correction
                dc = np.multiply(dc_raw, sgn(dc_theta)) / self.sqrt2
                # sign and Vrms->Vpk correction for linear polarization values
                lp = np.multiply(lp_raw, sgn(lp_theta)) * self.sqrt2 * self.bessel_corr_lp
                #linear polarization amplitude
                lp_r = lp_raw * self.sqrt2 * self.bessel_corr_lp                       

                #Calculate glum=2AC/DC
                g_lum = 2*np.divide(ac,dc)              
                #Calc I_L=(AC+DC)
                I_L = np.add(ac,dc)
                #Calc I_R=(DC-AC)
                I_R = np.subtract(dc,ac)  

                #The error of the values is calculates as the standard deviation in the data set that is collected for one wavelength
                if ac.shape[0] > 0:
                    return {'success': True,
                            'data': [
                                np.average(dc),
                                np.std(dc),
                                np.average(ac),
                                np.std(ac),                                
                                np.average(I_L),
                                np.std(I_L),
                                np.average(I_R),
                                np.std(I_R),
                                np.average(g_lum),
                                np.std(g_lum),
                                np.average(lp_r),
                                np.std(lp_r),
                                np.average(lp_theta),
                                np.std(lp_theta),
                                np.average(lp),
                                np.std(lp)]}
                else:
                    error = True
                    self.log('Error during calculation of corrected values and glum! Returning zeros. Printing raw data.',True)   
                    print(raw_data)
            else:
                error = True
                self.log('Error: All NaN in at least one of the channels (AC, DC, Theta, LP or LP theta)! Returning zeros. Printing raw data.',True)                    
                print(raw_data)
        else:
            error = True
            self.log('Missing data from MFLI. Returning zeros.',True)
        if error:
            return {'success': False,
                    'data': np.zeros(14)}
            
    #reads the phase of CPL, returns the average value
    def read_ac_theta(self, ext_abort_flag:list) -> float:
        path = self.devPath+'demods/0/sample'
        theta = []
        self.ac_theta_avg = 0.0
        self.ac_theta_count = 0

        self.log('Recording AC theta...')
        
        #This function uses poll instead of read for performance reasons. Also no temporal alignment of the data is required
        self.daq.subscribe(path)
        self.daq.sync()
        
        while not ext_abort_flag[0]:
            data_chunk = self.daq.poll(0.1, 50, 0, True)
            if path in data_chunk:
                x = data_chunk[path]['x']
                y = data_chunk[path]['y']
                new_theta = np.arctan2(y,x)*180/np.pi
                theta.extend(new_theta)
                self.ac_theta_avg = np.average(theta)
                self.ac_theta_count = len(theta)

        self.daq.unsubscribe('*')
        self.daq.sync()
        self.log('Stop recording AC theta...')
        ext_abort_flag[0] = False
        return self.ac_theta_avg
            


# In[44]:


#Dialog that guides the user through the phase offset calibration
class PhaseOffsetCalibrationDialog(LogObject):
    update_interval = 1000 #ms
    
    log_name = 'CAL'
    
    new_offset = 0.0
    current_average = 0.0
    current_datapoints_count = 0
    
    skipped_pos_cal = False
    skipped_neg_cal = False
    
    def __init__(self, ctrl):
        self.controller = ctrl
        self.log_queue = ctrl.log_queue
        
        #Setting up the window
        self.window = tk.Toplevel()
        self.window.title('Phaseoffset Calibration')
        self.window.resizable(False, False)
        self.window.configure(bg = "#EBFFE8")
        #stay on top of main window
        self.window.attributes('-topmost', 'true')
        #Disable X buttton
        self.window.protocol("WM_DELETE_WINDOW", self.disable_event)

        self.lbl_text = tk.Label(self.window, text='Insert a sample, move to a suitable wavelength and adjust gain to obtain strong positive CPL (e.g. Eu(facam)3 in DMSO at 613 nm)',  font=("Arial", 18), width=40,height=5,wraplength=600, bg = "#EBFFE8")
        self.lbl_text.pack()
        self.lbl_time = tk.Label(self.window, text='Time passed (>1200 s recommended): 0 s', font=("Arial", 14),bg = "#EBFFE8")
        self.lbl_time.pack()
        self.lbl_datapoints = tk.Label(self.window, text='Number of data points: 0', font=("Arial", 14),bg = "#EBFFE8")
        self.lbl_datapoints.pack()
        self.lbl_average = tk.Label(self.window, text='Average phase: 0 deg', font=("Arial", 14),bg = "#EBFFE8")
        self.lbl_average.pack()
        self.lbl_avg_pos = tk.Label(self.window, text='Average pos. phase: --', font=("Arial", 14),bg = "#EBFFE8")
        self.lbl_avg_pos.pack()
        self.lbl_avg_neg = tk.Label(self.window, text='Average neg. phase: --', font=("Arial", 14),bg = "#EBFFE8")
        self.lbl_avg_neg.pack()
        self.btn_next = tk.Button(self.window, text='Next', command=self.next_step, font=("Arial", 14))
        self.btn_next.pack()
        self.btn_skip = tk.Button(self.window, text='Skip', command=self.skip, font=("Arial", 14))
        self.btn_skip.pack()
        self.btn_close = tk.Button(self.window, text='Close', command=self.close, font=("Arial", 14))
        self.btn_close.pack()
        
        self.step = 0
        self.t0 = 0.0
        
    def next_step(self):
        self.step += 1
        
        if self.step == 1:
            self.lbl_text.config(text = 'Collecting phase of positive CPL ')
            self.t0 = time.time()
            self.window.after(self.update_interval, self.update_loop) 
            self.controller.cal_start_record_thread(positive=True)
            
        elif self.step == 2:
            self.controller.cal_stop_record()
            if self.skipped_pos_cal:
                self.lbl_avg_pos.config(text = 'Average pos. phase: skipped')
            else:
                current_values = self.controller.cal_get_current_values()
                self.lbl_avg_pos.config(text = 'Average pos. phase: {:.3f} deg'.format(current_values[0]))
            self.reset_labels()
            self.lbl_text.config(text = 'Insert a sample, move to a suitable wavelength and adjust gain to obtain strong negative CPL (e.g. Eu(facam)3 in DMSO at 595 nm)')                
            
        elif self.step == 3:
            self.lbl_text.config(text = 'Collecting phase of negative CPL')
            self.t0 = time.time()
            self.window.after(self.update_interval, self.update_loop) 
            self.controller.cal_start_record_thread(positive=False)
            
        elif self.step == 4:
            self.controller.cal_stop_record()
            #wait for cal_theta_thread to stop
            self.show_summary_after_thread()
            
        elif self.step == 5:
            self.controller.cal_apply_new()
            self.controller.cal_end()
            self.window.destroy()
    
    #wait for the measurement thread to finish before showing the results
    def show_summary_after_thread(self):
        if not self.controller.cal_theta_thread is None:
            if self.controller.cal_theta_thread.is_alive():
                self.window.after(100,self.show_summary_after_thread)
            else:
                self.show_summary()
        else:
            self.show_summary()
    
    def show_summary(self):
        if self.skipped_neg_cal:
            self.lbl_avg_neg.config(text = 'Average neg. phase: skipped')
        else:
            current_values = self.controller.cal_get_current_values()
            self.lbl_avg_neg.config(text = 'Average neg. phase: {:.3f} deg'.format(current_values[0]))
            
        self.new_offset = self.controller.cal_get_new_phaseoffset(self.skipped_pos_cal,self.skipped_neg_cal)
        self.btn_skip['state'] = 'disabled'
        
        if self.skipped_pos_cal and self.skipped_neg_cal:
            self.lbl_text.config(text = 'Calibration was skipped.')
            self.btn_next['state'] = 'disabled'
        else:
            self.lbl_text.config(text = 'The new phase offset was determined to: {:.3f} degrees. Do you want to apply this value?'.format(self.new_offset))
            self.btn_next.config(text = 'Save')
    
    def skip(self):
        if self.step == 0:
            self.log('Pos. phase: skipped')
            self.skipped_pos_cal = True
            self.step += 1
            self.next_step()
        elif self.step == 1:
            self.log('Pos. phase: skipped')            
            self.skipped_pos_cal = True
            self.next_step()
        elif self.step == 2:
            self.log('Neg. phase: skipped')            
            self.skipped_neg_cal = True
            self.step += 1
            self.next_step()                
        elif self.step == 3:
            self.log('Neg. phase: skipped')            
            self.skipped_neg_cal = True
            self.next_step()                
                
    def update_loop(self):
        if self.step in [1,3] and self.controller.cal_running:
            self.lbl_time.config(text = 'Time passed (>1200 s recommended): {:.0f} s'.format(time.time()-self.t0))
            current_values = self.controller.cal_get_current_values()
            self.lbl_average.config(text = 'Average phase: {:.3f} deg'.format(current_values[0]))
            self.lbl_datapoints.config(text = 'Number of data points: {}'.format(current_values[1]))
            self.window.after(self.update_interval, self.update_loop) 
    
    def reset_labels(self):
        self.lbl_time.config(text = 'Time passed (>1200 s recommended): 0 s')
        self.lbl_average.config(text = 'Average phase: 0 deg')
        self.lbl_datapoints.config(text = 'Number of data points: 0')
        
    def close(self):      
        self.log('Calibration aborted.')
        if self.step in [1,3]:
            self.controller.cal_stop_record()
        self.controller.cal_end_after_thread()
        
    def disable_event(self):
        pass
    


# In[45]:


#Combines the individual components and controls the main window
class Controller(LogObject):
    version = '1.0.1'
    
    lowpass_filter_risetime = 0.6 #s, depends on the timeconstant of the low pass filter
    shutdown_threshold = 2.95 #Vl
    osc_refresh_delay = 100 #ms
    log_update_interval = 200 #ms
    spec_refresh_delay = 1000 #ms
    move_delay = 0.2 #s, additional delay after changing wavelength
    
    #A warning is printed if one value of lp_theta_std is below the threshold
    #as this indicates the presence of linear polarization in the emission
    lp_theta_std_warning_threshold = 1.0
    
    input_ranges = ['0.003','0.010','0.030','0.100','0.300','1.000','3.000']
    
    log_name = 'CTRL'
    acquisition_running = False
    
    #Parameters to calculate approx. gain from control voltage of PMT, log(gain) = slope*pmt_voltage + offset, derived from manual
    pmt_slope = 4.913
    pmt_offset = 1.222
    max_gain = 885.6
    gain_norm = 4775.0
    
    max_volt_hist_lenght = 75# number of data points in the signal tuning graph
    edt_changed_color = '#FFBAC5'
    
    curr_spec = np.array([[],#wavelenght
                          [],#DC
                          [],#DC stddev                          
                          [],#AC
                          [],#AC stddev
                          [],#I_L
                          [],#I_L stddev
                          [],#I_R
                          [],#I_R stddev  
                          [],#glum
                          [],#glum stddev
                          [],#lp_r
                          [],#lp_r stddev
                          [],#lp theta
                          [],#lp theta stddev
                          [],#lp
                          []])#lp stddev
    index_ac = 3 #in curr_spec
    index_dc = 1
    index_glum = 9
    index_lp_theta = 13    
    
    #averaged spectrum during measurement
    avg_spec = np.array([[],#wavelenght
                          [],#DC
                          [],#AC
                          []])#glum
    
    #variables required for phase offset calibration
    cal_running = False
    cal_collecting = False
    cal_new_value = 0.0
    cal_theta_thread = None
    
    
    #---Start of initialization/closing section---    
    
    def __init__(self):   
        #Locks to prevent race conditions in multithreading
        self.pem_lock = th.Lock()
        self.mono_lock = th.Lock()
        self.lockin_daq_lock = th.Lock()
        self.lockin_osc_lock = th.Lock()
        
        #This trigger to stop spectra acquisition is a list to pass it by reference to the read_data thread
        self.stop_spec_trigger = [False]
        #For oscilloscope monitoring
        self.stop_osc_trigger = False
        #For phaseoffset calibration
        self.stop_cal_trigger = [False]
        self.spec_thread = None
        
        #Create window
        self.gui = gui.gui_script.GUI()
        self.log_queue = queue.Queue()
        self.log_box = self.gui.edt_debuglog
        self.assign_gui_events()
    
        if os.path.exists("last_params.txt"):
            self.load_last_settings()
        
        self.set_initialized(False)
        self.set_acquisition_running(False)    
    
        self.log_author_message()
        self.update_log()
        
        self.gui.window.mainloop()          
    
    def set_initialized(self,init):
        self.initialized = init
        self.gui.btn_init['state'] = self.gui.get_state_const(not self.initialized)
        self.gui.btn_close['state'] = self.gui.get_state_const(self.initialized)
        
        self.set_active_components()
        
    def load_last_settings(self):
        
        def re_search(key,text):
            res = re.search(key,text)
            if res is None:
                return ''
            else:
                return res.group(1)            
            
        f = open('last_params.txt', 'r')
        s = f.read()
        f.close()
        
        keywords = [r'Spectra Name = (.*)\n',
                    r'Start WL = ([0-9\.]*) nm\n',
                    r'End WL = ([0-9\.]*) nm\n',
                    r'Step = ([0-9\.]*) nm\n',
                    r'Dwell time = ([0-9\.]*) s\n',
                    r'Repetitions = ([0-9]*)\n',
                    r'Exc. slit = ([0-9\.]*) nm\n',
                    r'Em. slit = ([0-9\.]*) nm\n',
                    r'Exc. WL = ([0-9\.]*) nm\n',
                    r'Comment = (.*)\n',
                    r'AC-Blank-File = (.*)\n',
                    r'Phase offset = ([0-9\.]*) deg',
                    r'DC-Blank-File = (.*)\n',
                    r'Detector Correction File = (.*)\n']

        
        edts = [self.gui.edt_filename,
                self.gui.edt_start,
                self.gui.edt_end,
                self.gui.edt_step,
                self.gui.edt_dwell,
                self.gui.edt_rep,
                self.gui.edt_excSlit,
                self.gui.edt_emSlit,
                self.gui.edt_excWL,
                self.gui.edt_comment,
                self.gui.edt_ac_blank,
                self.gui.edt_phaseoffset,
                self.gui.edt_dc_blank,
                self.gui.edt_det_corr
               ]
        
        for i in range(0,len(keywords)):
            val = re_search(keywords[i],s)
            if val != '':
                self.set_edt_text(edts[i],val)
          
        blank = re_search('PEM off = ([01])\n',s)
        if blank == '1':
            self.gui.var_pem_off.set(1)
        else:
            self.gui.var_pem_off.set(0)
        
        input_range = re_search('Input range = ([0-9\.]*)\n',s)
        if input_range in self.input_ranges:
            self.gui.cbx_range.set(input_range)   
    
    def set_acquisition_running(self,b):
        self.acquisition_running = b       
        self.set_active_components()

    
    def init_devices(self):        
        try:           
            rm_pem = pyvisa.ResourceManager()
            self.log('Available COM devices: {}'.format(rm_pem.list_resources()))       
            self.log('Initialize PEM-200...')
            self.window_update()            

            self.pem_lock.acquire()
            self.pem = PEM()
            self.window_update()            
            b1 = self.pem.initialize(rm_pem,self.log_queue)
            self.pem_lock.release()
            self.window_update()
            self.log('')

            if b1:
                self.log('Initialize monochromator SP-2155...')
                rm_mono = pyvisa.ResourceManager()
                self.window_update()            
                self.mono_lock.acquire()
                self.mono = Mono()
                self.window_update()
                b2 = self.mono.initialize(rm_mono,self.log_queue)  
                self.mono_lock.release()
                self.window_update()            
                self.log('')

                if b2:
                    self.log('Initialize lock-in amplifier MFLI for data acquisition...')
                    self.window_update()            
                    self.lockin_daq_lock.acquire()
                    self.lockin_daq = MFLI('dev3902','LID',self.log_queue)
                    self.window_update()            
                    b3 = self.lockin_daq.connect()
                    self.window_update()            
                    b3 = b3 and self.lockin_daq.setup_for_daq(self.pem.bessel_corr, self.pem.bessel_corr_lp)    
                    self.update_PMT_voltage_edt(self.lockin_daq.pmt_volt)
                    self.lockin_daq_lock.release()
                    self.set_phaseoffset_from_edt()                    
                    self.window_update()
                    self.log('')

                    if b3:
                        self.log('Initialize lock-in amplifier MFLI for oscilloscope monitoring...')
                        self.window_update()            
                        self.lockin_osc_lock.acquire()
                        self.lockin_osc = MFLI('dev3902','LIA',self.log_queue)
                        self.window_update()            
                        b4 = self.lockin_osc.connect()
                        self.window_update()            
                        b4 = b4 and self.lockin_osc.setup_for_scope()
                        self.lockin_osc_lock.release()
                        self.max_volt_history = collections.deque(maxlen=self.max_volt_hist_lenght)
                        self.osc_refresh_delay = 100#ms
                        self.stop_osc_trigger = False
                        self.start_osc_monit()

                        if b4:
                            self.set_initialized(True)                            
                            self.move_nm(1000)

                            self.window_update()
                            self.log('')
                            self.log('Initialization complete!')
        except Exception as e:
            self.set_initialized(False)
            self.log('ERROR during initialization: {}!'.format(str(e)),True) 
            
    def disconnect_devices(self):
        self.log('')
        self.log('Closing connections to devices...')
        self.set_PMT_voltage(0.0)
        
        #stop everthing
        self.stop_osc_trigger = True
        self.stop_spec_trigger[0] = True
        self.stop_cal_trigger[0] = True
        #wait for threads to end
        time.sleep(0.5)
        try:
            self.pem.close()
            self.mono.close()
            self.lockin_daq.disconnect()
            self.lockin_osc.disconnect()
            self.log('Connections closed.')
            self.set_initialized(False)
        except Exception as e:
            self.log('Error while closing connections: {}.'.format(str(e)),True)                   
       
    def on_closing(self):
        if tk.messagebox.askokcancel("Quit", "Do you want to quit?"):
            if not self.spec_thread is None:
                if self.spec_thread.is_alive():
                    self.abort_measurement()
                    time.sleep(1)
            if not self.cal_theta_thread is None:
                if self.cal_theta_thread.is_alive():
                    self.cal_stop_record()
                    time.sleep(1)
                    
            self.save_params('last')
            
            if self.initialized:
                self.disconnect_devices()
            self.gui.window.destroy()            
            
    #---End of initialization/closing section---
            
            
            
    #--- Start of GUI section---
    
    def log_author_message(self):
        self.log('CatCPL v{}'.format(self.version), False, True)
        self.log('')
        self.log('Author: Winald R. Kitzmann', False, True)
        self.log('https://github.com/wkitzmann/CatCPL/', False, True)
        self.log('')
        self.log('CatCPL is distributed under the GNU General Public License 3.0 (https://www.gnu.org/licenses/gpl-3.0.html).', False, True)
        self.log('')
        self.log('Cite XX', False, True)        
        self.log('')
        self.log('')
        self.log('')        
    
    def assign_gui_events(self):
        #Device Setup
        self.gui.btn_init.config(command=self.click_init)
        self.gui.btn_close.config(command=self.disconnect_devices) 
        
        #Signal tuning
        self.gui.btn_set_PMT.config(command=self.click_set_pmt)
        self.sv_pmt = tk.StringVar(name="pmt")
        self.gui.edt_pmt.config(textvariable=self.sv_pmt)
        self.sv_pmt.trace('w', self.edt_changed)
        self.gui.edt_pmt.bind('<Return>', self.enter_pmt)
               
        self.gui.btn_set_gain.config(command=self.click_set_gain)
        self.sv_gain = tk.StringVar(name="gain")
        self.gui.edt_gain.config(textvariable=self.sv_gain)
        self.sv_gain.trace('w', self.edt_changed)
        self.gui.edt_gain.bind('<Return>', self.enter_gain)
        
        self.gui.btn_set_WL.config(command=self.click_set_signal_WL)  
        self.sv_WL = tk.StringVar(name="WL")
        self.gui.edt_WL.config(textvariable=self.sv_WL)
        self.sv_WL.trace('w', self.edt_changed)        
        self.gui.edt_WL.bind('<Return>', self.enter_signal_WL)
        
        self.gui.cbx_range.bind('<<ComboboxSelected>>', self.change_cbx_range)
        self.gui.btn_autorange.config(command=self.click_autorange)
        
        self.gui.btn_set_phaseoffset.config(command=self.click_set_phaseoffset) 
        self.sv_phaseoffset = tk.StringVar(name="phaseoffset")
        self.gui.edt_phaseoffset.config(textvariable=self.sv_phaseoffset)
        self.sv_phaseoffset.trace('w', self.edt_changed)        
        self.gui.edt_phaseoffset.bind('<Return>', self.enter_phaseoffset)    
        
        self.gui.btn_cal_phaseoffset.config(command=self.click_cal_phaseoffset)
        
        #Spectra Setup
        self.gui.btn_start.config(command=self.click_start_spec) 
        self.gui.btn_abort.config(command=self.click_abort_spec)    
    
        self.gui.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    #(de)activate buttons and text components depending on the state of the software
    def set_active_components(self):
        self.gui.btn_init['state'] = self.gui.get_state_const(not self.initialized)
        self.gui.btn_close['state'] = self.gui.get_state_const(self.initialized)
        self.gui.set_spectra_setup_enable(not self.acquisition_running and self.initialized and not self.cal_running)
        self.gui.set_signal_tuning_enable(not self.acquisition_running and self.initialized and not self.cal_collecting) 
        self.gui.btn_start['state'] = self.gui.get_state_const(not self.acquisition_running and self.initialized and not self.cal_running)      
        self.gui.btn_abort['state'] = self.gui.get_state_const(self.acquisition_running and self.initialized and not self.cal_running)
        self.gui.btn_cal_phaseoffset['state'] = self.gui.get_state_const(not self.acquisition_running and self.initialized and not self.cal_running)      
        self.gui.set_cat_visible(self.initialized)
        self.update_mfli_status(self.initialized)
        self.update_initialized_status(self.initialized)
    
    def window_update(self):
        self.gui.window.update() 
    
    def update_log(self):
        #Handle all log messages currently in the queue, if any
        while self.log_queue.qsize():
            try:
                msg = self.log_queue.get(0)
                self.log_box.insert(tk.END,msg+'\n')
                self.log_box.see(tk.END)
            except queue.Empty:
                pass    
        self.gui.window.after(self.log_update_interval, self.update_log)

    #When the user changes a value in one of the text boxes in the Signal Tuning area
    #the text box is highlighed until the value is saved
    def edt_changed(self, var, index, mode):
        if var == 'pmt':
            edt = self.gui.edt_pmt
        elif var == 'gain':
            edt = self.gui.edt_gain
        elif var == 'WL':
            edt = self.gui.edt_WL
        elif var == 'phaseoffset':
            edt = self.gui.edt_phaseoffset          
        
        edt.config(bg=self.edt_changed_color)
    
    def set_PMT_volt_from_edt(self):
        try:
            v = float(self.gui.edt_pmt.get())
            if (v <= 1.1) and (v >= 0.0):
                self.set_PMT_voltage(v)
        except ValueError as e:
            self.log('Error in set_PMT_voltage_from_edt: '+str(e),True)        

    def set_gain_from_edt(self):
        try:
            g = float(self.gui.edt_gain.get())
            if (g<=self.max_gain):
                self.set_PMT_voltage(self.gain_to_volt(g))
        except ValueError as e:
            self.log('Error in set_gain_from_edt: '+str(e),True)    
            
    def set_WL_from_edt(self):
        try:
            nm = float(self.gui.edt_WL.get())
            self.move_nm(nm)
        except ValueError as e:
            self.log('Error in set_WL_from_edt: '+str(e),True)        

    def set_phaseoffset_from_edt(self):
        try:
            #if slef.gui.edt_phaseoffset.get() == '':
             #   po = 0
            po = float(self.gui.edt_phaseoffset.get())
            self.set_phaseoffset(po)
            self.gui.edt_phaseoffset.config(bg='#FFFFFF')
        except ValueError as e:
            self.log('Error in set_phaseoffset_from_edt: '+str(e),True)          
            
    def click_init(self):
        #deactivate init button
        self.gui.btn_init['state'] = self.gui.get_state_const(False)        
        self.init_devices()
        
    def click_set_pmt(self):
        self.set_PMT_volt_from_edt()
            
    def enter_pmt(self,event):
        self.click_set_pmt()             
    
    def click_set_gain(self):
        self.set_gain_from_edt()
    
    def enter_gain(self,event):
        self.click_set_gain()            

    def click_set_signal_WL(self):
        self.set_WL_from_edt()
    
    def enter_signal_WL(self,event):
        self.click_set_signal_WL()
        
    def change_cbx_range(self,event):
        self.set_input_range(float(self.gui.cbx_range.get()))
        
    def click_autorange(self):
        self.set_auto_range()        
        
    def click_set_phaseoffset(self):
        self.set_phaseoffset_from_edt()
        
    def enter_phaseoffset(self,event):
        self.click_set_phaseoffset()
    
    def click_cal_phaseoffset(self):
        self.cal_phaseoffset_start()
    
    def click_start_spec(self):
        self.start_spec()
        
    def click_abort_spec(self):
        self.abort_measurement()   
        
    def update_phaseoffset_edt(self,value:float):
        self.set_edt_text(self.gui.edt_phaseoffset,'{:.3f}'.format(value))
    
    def update_progress_txt(self,start:float,stop:float,curr:float,run:int,run_count:int,time_since_start:float):
        #Calculate progress in percent
        if stop > start:
            f = (1-(stop-curr)/(stop-start))*100
        else:
            f = (1-(curr-stop)/(start-stop))*100
        
        #Remaining time is estimated from progress+passed time
        time_left = 0       
        if f>0:
            time_left = (run_count*100/(f+100*(run-1))-1)*time_since_start        
            
        #Determine proper way to display the estimated remaining time            
        if time_left < 60:
            unit = 's'
        elif time_left < 3600:
            unit = 'min'
            time_left = time_left/60
        else:
            unit = 'h'
            time_left = time_left/3600
        
        #Update label text
        self.gui.canvas.itemconfigure(self.gui.txt_progress, text='{:.1f} % ({:d}/{:d}), ca. {:.1f} {}'.format(f,run,run_count,time_left,unit))
    
    def update_initialized_status(self,b:bool):
        if b:
            self.gui.canvas.itemconfigure(self.gui.txt_init, text='True')
        else:
            self.gui.canvas.itemconfigure(self.gui.txt_init, text='False')
    
    def update_mfli_status(self,b:bool):
        if b:
            self.gui.canvas.itemconfigure(self.gui.txt_mfli, text='connected')
        else:
            self.gui.canvas.itemconfigure(self.gui.txt_mfli, text='-')
            
    def update_osc_captions(self,curr:float,label):
        if not np.isnan(curr):
            self.gui.canvas.itemconfigure(label, text='{:.1e} V'.format(curr))
    
    def update_osc_plots(self,max_vals):
        self.gui.plot_osc(data_max=max_vals,max_len=self.max_volt_hist_lenght,time_step=self.osc_refresh_delay)            

    def update_PMT_voltage_edt(self,volt):
        self.set_edt_text(self.gui.edt_pmt,'{:.3f}'.format(volt))
        self.set_edt_text(self.gui.edt_gain,'{:.3f}'.format(self.volt_to_gain(volt)))  
        self.gui.edt_pmt.config(bg='#FFFFFF')
        self.gui.edt_gain.config(bg='#FFFFFF')        
        self.window_update()    
        
    def update_mono_edt_lbl(self,wl):
        self.gui.canvas.itemconfigure(self.gui.txt_mono, text='{:.2f} nm'.format(wl))
        self.set_edt_text(self.gui.edt_WL,'{:.2f}'.format(wl))     
        self.gui.edt_WL.config(bg='#FFFFFF') 
            
    def update_pem_lbl(self,wl):
        self.gui.canvas.itemconfigure(self.gui.txt_PEM, text='{:.2f} nm'.format(wl))
        
    def set_edt_text(self,edt,s):
        state_before = edt['state']
        edt['state'] = self.gui.get_state_const(True)
        edt.delete(0,tk.END)
        edt.insert(0,s)
        edt['state'] = state_before     
        
    def update_spec(self): 
        if self.acquisition_running:
            self.gui.plot_spec(
                tot=[self.curr_spec[0],self.curr_spec[self.index_dc]],
                tot_avg=[self.avg_spec[0],self.avg_spec[1]],
                cpl=[self.curr_spec[0],self.curr_spec[self.index_ac]],
                cpl_avg=[self.avg_spec[0],self.avg_spec[2]],
                glum=[self.curr_spec[0],self.curr_spec[self.index_glum]],
                glum_avg=[self.avg_spec[0],self.avg_spec[3]],)
        
        if not self.spec_thread is None:
            if self.spec_thread.is_alive():
                self.gui.window.after(self.spec_refresh_delay,self.update_spec)                        
                
    #----End of GUI section---
    
    
    
    #---Start of spectra acquisition section---
        
    def start_spec(self): 
        
        def filename_exists_or_empty(name: str) -> bool:
            if name == '':
                return True
            else:
                return os.path.exists(".\\data\\"+name+".csv")
            
        def check_illegal_chars(s):
            result = False
            for c in s:
                if c in '#@$%^&*{}:;"|<>/?\`~'+"'":
                    result = True
                    break
            return result
        
        ac_blank = self.gui.edt_ac_blank.get()
        dc_blank = self.gui.edt_dc_blank.get()
        det_corr = self.gui.edt_det_corr.get()
        filename = self.gui.edt_filename.get()
        reps = int(self.gui.edt_rep.get())
        
        ac_blank_exists = filename_exists_or_empty(ac_blank)
        dc_blank_exists = filename_exists_or_empty(dc_blank)
        det_corr_exists = filename_exists_or_empty(det_corr)
        
        if not check_illegal_chars(filename):
            try:
                #For averaged measurements add the suffix of the first scan for the filename check
                if reps == 1:
                    s = ''
                else:
                    s = '_1'
                filename_exists = filename_exists_or_empty(filename+s)

                error = not ac_blank_exists or not dc_blank_exists or not det_corr_exists or filename_exists
                
                if not error:
                    self.stop_spec_trigger[0] = False

                    self.set_acquisition_running(True)

                    self.spec_thread = th.Thread(target=self.record_spec,args=(
                        float(self.gui.edt_start.get()),
                        float(self.gui.edt_end.get()),
                        float(self.gui.edt_step.get()),
                        float(self.gui.edt_dwell.get()),
                        reps,
                        filename,
                        ac_blank,
                        dc_blank,
                        det_corr,
                        self.gui.var_pem_off.get()))
                    self.spec_thread.start() 
                    self.update_spec()
                else:
                    if not ac_blank_exists:
                        self.log('Error: AC-blank file does not exist!',True)
                    if not dc_blank_exists:
                        self.log('Error: DC-blank file does not exist!',True)
                    if not det_corr_exists:
                        self.log('Error: Detector correction file does not exist!',True)
                    if filename_exists:
                        self.log('Error: Spectra filename {} already exists!'.format(filename+s),True)
            except Exception as e:
                self.log('Error in click_start_spec: '+str(e),True)
        else:
            self.log('Error: Filename contains one of these illegal characters: '+'#@$%^&*{}:;"|<>/?\`~'+"'")
    
    #will be executed in separate thread
    def record_spec(self,start_nm:float,end_nm:float,step:float,dwell_time:float,reps:int,filename:str,ac_blank:str,dc_blank:str,det_corr:str,pem_off:int):
        
        def check_lp_theta_std(lp:float) -> bool:
            if lp < self.lp_theta_std_warning_threshold:
                self.log('Warning: Possibly linearly polarized emisssion at {:.2f} (lp_theta_std = {:.3f})!'.format(curr_nm,lp),False)
                return True
            else:
                return False
        
        #try:
        self.log('')
        self.log('Spectra acquisition: {:.2f} to {:.2f} nm with {:.2f} nm steps and {:.3f} s per step'.format(start_nm,end_nm,step,dwell_time))                     

        self.log('Starting data acquisition.')
        
        self.lockin_daq_lock.acquire()
        self.lockin_daq.set_dwell_time(dwell_time)
        self.lockin_daq_lock.release()
        
        #wait for MFLI buffer to be ready
        self.interruptable_sleep(dwell_time)

        #array of pandas dataframes with all spectral data
        dfall_spectra = np.empty(reps, dtype=object)
        #avg_spec is used to display the averaged spectrum during the measurement
        self.avg_spec = np.array([[],#wavelength
                     [],#DC
                     [],#AC
                     []])#glum

        correction = ac_blank != '' or dc_blank != '' or det_corr != ''

        if start_nm > end_nm:
            inc = -step
        else:
            inc = step   
        direction = np.sign(inc)

        self.update_progress_txt(0,1,0,1,reps,0)

        #Disable PEM for AC background measurement
        self.set_modulation_active(pem_off == 0)

        time_since_start = -1.0
        t0 = time.time()

        i = 0
        while (i<reps) and not self.stop_spec_trigger[0]:
            self.log('')
            self.log('Run {}/{}'.format(i+1,reps))

            lp_detected = False

            self.curr_spec = np.array([[],#wavelenght
                                      [],#AC
                                      [],#AC stddev
                                      [],#DC
                                      [],#DC stddev
                                      [],#I_L
                                      [],#I_L stddev
                                      [],#I_R
                                      [],#I_R stddev  
                                      [],#glum
                                      [],#glum stddev
                                      [],#lp_r
                                      [],#lp_r stddev
                                      [],#lp theta
                                      [],#lp theta stddev
                                      [],#lp 
                                      []])#lp stddev

            #self.log('start {}'.format(time.time()-t0))
            curr_nm = start_nm-inc          
            while ((((direction > 0) and (curr_nm < end_nm)) or ((direction < 0) and (curr_nm > end_nm)))
                   and not self.stop_spec_trigger[0]):                                

                curr_nm = curr_nm+inc
                #self.log('before move {:.3f}'.format(time.time()-t0))
                self.move_nm(curr_nm,pem_off == 0)
                #self.log('after move {:.3f}'.format(time.time()-t0))

                self.interruptable_sleep(self.lowpass_filter_risetime)
                #self.log('afer risetime {:.3f}'.format(time.time()-t0))

                #try three times to get a successful measurement
                j = 0
                success = False
                #Try 5 times to get a valid dataset from the MFLI
                while (j<5) and not success and not self.stop_spec_trigger[0]:  
                    #self.log('before acquire {:.3f}'.format(time.time()-t0))
                    self.lockin_daq_lock.acquire()
                    #self.log('afer lock {:.3f}'.format(time.time()-t0))
                    data = self.lockin_daq.read_data(self.stop_spec_trigger)
                    #self.log('after read {:.3f}'.format(time.time()-t0))
                    self.lockin_daq_lock.release()

                    if not self.stop_spec_trigger[0]:
                        #Check if there is a linearly polarized component (2f) in the signal
                        lp_detected = lp_detected or check_lp_theta_std(data['data'][self.index_lp_theta])                    
                        #self.log('afeter release {:.3f}'.format(time.time()-t0))
                        success = data['success']
                    j += 1

                if not success and not self.stop_spec_trigger[0]:
                    self.stop_spec_trigger[0] = True
                    self.log('Could not collect data after 5 tries, aborting...',True)

                if not self.stop_spec_trigger[0]:
                    #add current wavelength to dataset
                    data_with_WL = np.array([np.concatenate(([curr_nm],data['data']))])
                    #add dataset to current spectrum
                    self.curr_spec = np.hstack((self.curr_spec, data_with_WL.T))
                    if reps > 1:
                        self.add_data_to_avg_spec(data_with_WL,i)

                time_since_start = time.time()-t0
                self.update_progress_txt(start_nm,end_nm,curr_nm,i+1,reps,time_since_start)
                #self.log('before next step {:.3f}'.format(time.time()-t0))

            if self.stop_spec_trigger[0]:
                self.set_PMT_voltage(0.0)

            self.log('This scan took {:.0f} s.'.format(time_since_start))

            #process spectra as dataframes (df)
            dfcurr_spec = self.np_to_pd(self.curr_spec)
            if reps > 1:
                index_str = '_'+str(i+1)
            else:
                index_str = ''                
            self.save_spec(dfcurr_spec,filename+index_str)

            if correction:
                dfcurr_spec_corr = self.apply_corr(dfcurr_spec,ac_blank,dc_blank,det_corr)
                self.save_spec(dfcurr_spec_corr,filename+index_str+'_corr',False)

            dfall_spectra[i] = dfcurr_spec

            if lp_detected:
                self.log('')
                self.log('Warning: Possibly linearly polarized emission!', True)

            i += 1

        self.log('Stopping data acquisition.')
        self.set_acquisition_running(False)

        #averaging and correction of the averaged spectrum
        if reps > 1 and not self.stop_spec_trigger[0]:
            dfavg_spec = self.df_average_spectra(dfall_spectra)
            self.save_spec(dfavg_spec,filename+'_avg',False)      

            if correction:
                dfavg_spec_corr = self.apply_corr(dfavg_spec_recalc,ac_blank,dc_blank,det_corr)
                self.save_spec(dfavg_spec_corr,filename+'_avg_corr',False)            

        self.log('')
        self.log('Returning to start wavelength')
        self.set_modulation_active(True)
        self.move_nm(start_nm,move_pem=True)

        self.stop_spec_trigger[0] = False
        #except Exception as e:
            #self.log("Error in record_spec: {}".format(str(e)))
    
    def interruptable_sleep(self,t:float):
        start = time.time()
        while (time.time()-start < t) and not self.stop_spec_trigger[0]:
            time.sleep(0.01)

    def add_data_to_avg_spec(self,data,curr_rep:int):
        #avg_spec structure: [[WL],[DC],[AC],[glum]] 
        if curr_rep == 0:
            self.avg_spec = np.hstack((self.avg_spec, np.array(([data[0][0]],[data[0][self.index_dc]],[data[0][self.index_ac]],[data[0][self.index_glum]]))))
        else:
            #find index where the wavelength of the new datapoint matches
            index = np.where(self.avg_spec[0] == data[0][0])[0] 
            if len(index) > 0:
                #reaverage DC and AC
                self.avg_spec[1][index[0]] = (self.avg_spec[1][index[0]]*curr_rep + data[0][self.index_dc])/(curr_rep+1)
                self.avg_spec[2][index[0]] = (self.avg_spec[2][index[0]]*curr_rep + data[0][self.index_ac])/(curr_rep+1)
                #recalculate glum
                self.avg_spec[3][index[0]] = 2*self.avg_spec[2][index[0]]/self.avg_spec[1][index[0]]            

    #converts a numpy array to a pandas DataFrame
    def np_to_pd(self,spec):
        df = pd.DataFrame(spec.T)
        df.columns = ['WL','DC','DC_std','AC','AC_std','I_L','I_L_std','I_R','I_R_std','glum','glum_std','lp_r','lp_r_std','lp_theta','lp_theta_std','lp','lp_std']       
        df = df.set_index('WL')
        return df
        
    def df_average_spectra(self,dfspectra):      
        self.log('')
        self.log('Averaging...')
        #create a copy of the Dataframe structure of a spectrum filled with zeros
        dfavg = dfspectra[0].copy()
        dfavg.iloc[:,:] = 0.0
        
        count = len(dfspectra)
        #The error of the averaged spectrum is estimated using Gaussian propagation of uncertainty
        for i in range(0,count):
            dfavg['DC'] = dfavg['DC'] + dfspectra[i]['DC']/count
            dfavg['DC_std'] = dfavg['DC_std'] + (dfspectra[i]['DC_std']/count)**2
            dfavg['AC'] = dfavg['AC'] + dfspectra[i]['AC']/count
            dfavg['AC_std'] = dfavg['AC_std'] + (dfspectra[i]['AC_std']/count)**2            
            dfavg['lp_r'] =  dfavg['lp_r'] + dfspectra[i]['lp_r']/count
            dfavg['lp_r_std'] = dfavg['lp_r_std'] + (dfspectra[i]['lp_r_std']/count)**2
            dfavg['lp_theta'] =  dfavg['lp_theta'] + dfspectra[i]['lp_theta']/count
            dfavg['lp_theta_std'] = dfavg['lp_theta_std'] + (dfspectra[i]['lp_theta_std']/count)**2
            dfavg['lp'] =  dfavg['lp'] + dfspectra[i]['lp']/count
            dfavg['lp_std'] = dfavg['lp_std'] + (dfspectra[i]['lp_std']/count)**2            
        dfavg['AC_std'] = dfavg['AC_std']**(0.5)
        dfavg['DC_std'] = dfavg['DC_std']**(0.5)
        dfavg['lp_r_std'] = dfavg['lp_r_std']**(0.5)
        dfavg['lp_theta_std'] = dfavg['lp_theta_std']**(0.5)
        dfavg['lp_std'] = dfavg['lp_std']**(0.5)
        
        dfavg = self.calc_cpl(dfavg)  
            
        return dfavg
    
    def apply_corr(self,dfspec:pd.DataFrame,ac_blank:str,dc_blank:str,det_corr:str):
        
        #Gives True if wavelength region is suitable
        def is_suitable(df_corr:pd.DataFrame, check_index:bool) -> bool:
            first_WL_spec = dfspec.index[0]
            last_WL_spec = dfspec.index[-1]
            
            first_WL_corr = df_corr.index[0]
            last_WL_corr = df_corr.index[-1]
            
            #Check if the wavelength region in dfspec is covered by df_det_corr
            WL_region_ok = min(first_WL_spec,last_WL_spec)>=min(first_WL_corr,last_WL_corr) and max(first_WL_spec,last_WL_spec)<=max(first_WL_corr,last_WL_corr)
            #Check if the measured wavelength values are available in the correction file (for AC and DC without interpolation)
            values_ok = not check_index or dfspec.index.isin(df_corr.index).all()
            
            return WL_region_ok and values_ok
            
        #Interpolate the detector correction values to match the measured wavelength values 
        def interpolate_detcorr():
            #Create a copy of the measured wavelengths and fill it with NaNs
            dfspec_nan = pd.DataFrame()
            dfspec_nan['nan'] = dfspec['AC'].copy()
            dfspec_nan.iloc[:,0] = float('NaN')
            
            nonlocal df_det_corr            
            #Add the measured wavelengths to the correction data, missing values in the correction data will be set to NaN
            df_det_corr = pd.concat([df_det_corr, dfspec_nan], axis=1).drop('nan',axis=1)
            #Interpolate missing values in the correction data
            df_det_corr = df_det_corr.interpolate(method='index')
            #Limit WL values of correction data to measured wavelengths
            df_det_corr = df_det_corr.filter(items = dfspec_nan.index, axis=0)
            
        self.log('')
        self.log('Baseline correction...')
        
        #Correction for detector sensitivity
        #Todo global data path
        if det_corr != '':
            self.log('Detector sensitivity correction with {}'.format(".\\data\\"+det_corr+".csv"))
            df_det_corr = pd.read_csv(filepath_or_buffer=".\\data\\"+det_corr+".csv", sep=',', index_col='WL')
            
            if is_corr_suitable(df_det_corr,False):
                interpolate_detcorr()
                dfspec['DC'] = dfspec['DC']/df_det_corr.iloc[:,0]
                dfspec['DC_std'] = dfspec['DC_std']/df_det_corr.iloc[:,0]
                dfspec['AC'] = dfspec['AC']/df_det_corr.iloc[:,0]            
                dfspec['AC_std'] = dfspec['AC_std']/df_det_corr.iloc[:,0]   
            else:
                self.log('Detector correction file does not cover the measured wavelength range!',True)
        
        #AC baseline correction 
        if ac_blank != '':
            self.log('AC blank correction with {}'.format(".\\data\\"+ac_blank+".csv"))
            df_ac_blank = pd.read_csv(filepath_or_buffer=".\\data\\"+ac_blank+".csv", sep=',', index_col='WL')
            
            if is_corr_suitable(df_ac_blank,True):
                dfspec['AC'] = dfspec['AC'] - df_ac_blank['AC']
                dfspec['AC_std'] = ((dfspec['AC_std']/2)**2 + (df_ac_blank['AC_std']/2)**2)**0.5
            else:
                self.log('AC blank correction file does not contain the measured wavelengths!',True)                
        
        #DC baseline correction
        if dc_blank != '':
            self.log('DC blank correction with {}'.format(".\\data\\"+dc_blank+".csv"))
            df_dc_blank = pd.read_csv(filepath_or_buffer=".\\data\\"+dc_blank+".csv", sep=',', index_col='WL')
            
            if is_corr_suitable(df_dc_blank,True):
                dfspec['DC'] = dfspec['DC'] - df_dc_blank['DC']
                dfspec['DC_std'] = ((dfspec['DC_std']/2)**2 + (df_dc_blank['DC_std']/2)**2)**0.5
            else:
                self.log('DC blank correction file does not contain the measured wavelengths!',True)             
            
        #If there are wavelength values in the blankfiles that are not in dfspec this will give NaN values
        #Drop all rows that contain NaN values
        #The user must make sure that the blank files contain the correct values for the measurement
        dfspec = dfspec.dropna(axis=0)
        
        dfspec = self.calc_cpl(dfspec)
        return dfspec
        
    def calc_cpl(self,df):
        df['I_L'] = (df['AC'] + df['DC'])
        df['I_R'] = (df['DC'] - df['AC'])
        df['glum'] = 2*df['AC']/df['DC']
        #Gaussian error progression
        df['I_L_std'] = ((df['AC_std'])**2 + (df['DC_std'])**2)**0.5
        df['I_R_std'] = df['I_L_std'].copy()
        df['glum_std'] = ((2*df['AC_std']/df['DC'])**2 + (2*df['AC']/(df['DC']**2)*df['DC_std'])**2)**0.5        
        return df
    
    def save_spec(self,dfspec,filename,savefig=True):
        dfspec.to_csv(".\\data\\"+filename+'.csv',index=True)
        self.log('Data saved as: {}'.format(".\\data\\"+filename+'.csv'))
        self.save_params(".\\data\\"+filename)
        if savefig:
            self.gui.spec_fig.savefig(".\\data\\"+filename+'.png')
            self.log('Figure saved as: {}'.format(".\\data\\"+filename+'.png'))                 
                 
    def save_params(self,filename):
        with open(filename+'_params.txt', 'w') as f:
            f.write('Specta Name = {}\n'.format(self.gui.edt_filename.get()))
            f.write('Time = {}\n\n'.format(time.asctime(time.localtime(time.time()))))
            f.write('Setup parameters\n')        
            f.write('Start WL = {} nm\n'.format(self.gui.edt_start.get()))
            f.write('End WL = {} nm\n'.format(self.gui.edt_end.get()))
            f.write('Step = {} nm\n'.format(self.gui.edt_step.get()))
            f.write('Dwell time = {} s\n'.format(self.gui.edt_dwell.get()))
            f.write('Repetitions = {}\n'.format(self.gui.edt_rep.get()))
            f.write('Exc. slit = {} nm\n'.format(self.gui.edt_excSlit.get()))
            f.write('Em. slit = {} nm\n'.format(self.gui.edt_emSlit.get()))
            f.write('Exc. WL = {} nm\n'.format(self.gui.edt_excWL.get()))
            f.write('Comment = {}\n'.format(self.gui.edt_comment.get()))
            f.write('AC-Blank-File = {}\n'.format(self.gui.edt_ac_blank.get()))
            f.write('DC-Blank-File = {}\n'.format(self.gui.edt_dc_blank.get()))
            f.write('PEM off = {:d}\n'.format(self.gui.var_pem_off.get()))
            f.write('Detector Correction File = {}\n'.format(self.gui.edt_det_corr.get()))
            f.write('PMT voltage = {} V\n'.format(self.gui.edt_pmt.get()))
            f.write('PMT gain = {}\n'.format(self.gui.edt_gain.get()))
            f.write('Input range = {}\n'.format(self.gui.cbx_range.get()))
            f.write('Phase offset = {} deg\n'.format(self.gui.edt_phaseoffset.get()))
            f.close()
        self.log('Parameters saved as: {}'.format(".\\data\\"+filename+'_params.txt'))
    
    def abort_measurement(self):
        self.log('')
        self.log('>>Aborting measurement<<')
        
        self.stop_spec_trigger[0] = True
        self.reactivate_after_abort()
    
    def reactivate_after_abort(self):
        if not self.spec_thread is None:
            if self.spec_thread.is_alive():
                self.gui.window.after(500, self.reactivate_after_abort)
            else:
                self.set_acquisition_running(False)
        else:
            self.set_acquisition_running(False)
            
    #---end of spectra acquisition section---
                
        
        
    #---Control functions start---
    
    def set_modulation_active(self,b):
        #deactivating phase-locked loop on PEM reference in lock-in to retain last PEM frequency
        self.lockin_daq_lock.acquire()
        self.lockin_daq.set_extref_active(0,b)
        self.lockin_daq.daq.sync()
        self.lockin_daq_lock.release()

        #deactivating pem will cut off reference signal and modulation
        self.pem_lock.acquire()
        self.pem.set_active(b)         
        self.pem_lock.release()
        if not b:
            self.gui.canvas.itemconfigure(self.gui.txt_PEM, text='off')
    
    def set_phaseoffset(self,value):
        if initialized:
            self.lockin_daq_lock.acquire()
            self.lockin_daq.set_phaseoffset(value)
            self.lockin_daq_lock.release()
  
    def move_nm(self,nm,move_pem=True):
        self.log('')
        self.log('Move to {} nm'.format(nm))
        if self.initialized:              
            #The WL changes in PEM and Monochromator are done in separate threads to save time
            mono_thread = th.Thread(target=self.mono_move, args=(nm,))
            mono_thread.start()
            
            if move_pem:
                self.pem_lock.acquire()
                self.pem.set_nm(nm)   
                self.pem_lock.release()
                self.update_pem_lbl(nm)
                
            while mono_thread.is_alive():
                time.sleep(0.02)
                
            self.update_mono_edt_lbl(nm)
            
            if self.acquisition_running:
                self.interruptable_sleep(self.move_delay)
            else:
                time.sleep(self.move_delay)
        else:
            self.log('Instruments not initialized!',True)
    
    def mono_move(self,nm):
        self.mono_lock.acquire()
        self.mono.set_nm(nm)
        self.mono_lock.release()
    
    def volt_to_gain(self,volt):
        return 10**(volt*self.pmt_slope + self.pmt_offset)/self.gain_norm
    
    def gain_to_volt(self,gain):
        if gain<1.0:
            return 0.0
        elif gain>=self.max_gain:
            return 1.1
        else:
            return max(min((math.log10(gain*self.gain_norm)-self.pmt_offset)/self.pmt_slope,1.1),0.0)
    
    def set_PMT_voltage(self, volt):
        try:
            self.lockin_daq_lock.acquire()
            self.lockin_daq.set_PMT_voltage(volt,False)
            self.lockin_daq_lock.release()
            
            self.update_PMT_voltage_edt(volt)
        except Exception as e:
            self.log('Error in set_PMT_voltage: '+str(e),True)
    
    def rescue_pmt(self):
        self.log('Signal ({:.2f} V) higher than threshold ({:.2f} V)!! Setting PMT to 0 V'.format(self.max_volt,self.shutdown_threshold),True)
        self.set_PMT_voltage(0.0)  
    
    def set_input_range(self,f):
        self.lockin_daq_lock.acquire()
        self.lockin_daq.set_input_range(f=f,auto=False)
        self.lockin_daq_lock.release()
    
    def set_auto_range(self):
        self.lockin_daq_lock.acquire()
        self.lockin_daq.set_input_range(f=0.0,auto=True)
        self.gui.cbx_range.set('{:.3f}'.format(self.lockin_daq.signal_range))
        self.lockin_daq_lock.release()
    
    def set_phaseoffset(self,f):
        self.lockin_daq_lock.acquire()
        self.lockin_daq.set_phaseoffset(f)
        self.update_phaseoffset_edt(f)
        self.lockin_daq_lock.release()            
    
    #---control functions end---
    
    
    
    #---oscilloscope section start---
    
    def start_osc_monit(self):
        self.stop_osc_trigger = False
        self.max_volt = 0.0
        self.avg_volt = 0.0
        
        self.lockin_osc_lock.acquire()
        self.lockin_osc.start_scope()
        self.lockin_osc_lock.release()
        self.monit_thread = th.Thread(target=self.monit_osc_loop)
        self.monit_thread.start()   
        
        self.refresh_osc()
    
    def refresh_osc(self):
        self.update_osc_captions(self.max_volt,self.gui.txt_maxVolt)     
        self.update_osc_captions(self.avg_volt,self.gui.txt_avgVolt)  
        self.update_osc_plots(max_vals=np.asarray(self.max_volt_history))
        if self.monit_thread.is_alive():
            self.gui.window.after(self.osc_refresh_delay,self.refresh_osc)
    
    #Collects current max. voltage in self.max_volt_history, will be executed in separate thread
    def monit_osc_loop(self):
        while not self.stop_osc_trigger:
            time.sleep(self.osc_refresh_delay/1000)
            
            self.lockin_osc_lock.acquire()
            scope_data = self.lockin_osc.read_scope()
            self.lockin_osc_lock.release()
            
            self.max_volt = scope_data[0]
            self.avg_volt = scope_data[1]            
            if not np.isnan(self.max_volt):
                self.max_volt_history.append(self.max_volt)
                
                #Check if value reached input range limit by checking if the last 5 values are the same and
                #close to input range (>95%)     
                if len(self.max_volt_history) >= 5:
                    range_limit_reached = True 
                    for i in range(2,6):
                        range_limit_reached = range_limit_reached and (math.isclose(self.max_volt_history[-i],self.max_volt,abs_tol=0.000000001)
                            and (self.max_volt_history[-i]>=0.95*self.lockin_daq.signal_range))
                    
                    #Check if value too high (may cause damage to PMT) for several consecutive values
                    pmt_limit_reached = True
                    for i in range(1,4):
                        pmt_limit_reached = pmt_limit_reached and (self.max_volt_history[-i] >= self.shutdown_threshold)
                        
                    if range_limit_reached:
                        self.set_auto_range()
                        if self.acquisition_running:
                            self.log('Input range limit reached during measurement! Restart with higher input range or lower gain. Aborting...', True)
                            self.abort_measurement()                        
                    if pmt_limit_reached:
                        self.rescue_pmt()
                        if self.acquisition_running:
                            self.abort_measurement()
                    
        if self.stop_osc_trigger:
            self.lockin_osc_lock.acquire()
            self.lockin_osc.stop_scope()
            self.lockin_osc_lock.release()
            
            self.stop_osc_trigger = False
                
    #---oscilloscope section end---    
    
    
    
    #---Phase offset calibration section start---
    
    def cal_phaseoffset_start(self):
        self.log('')
        self.log('Starting calibration...')
        self.log('Current phaseoffset: {:.3f} deg'.format(self.lockin_daq.phaseoffset))
        
        self.cal_running = True
        self.cal_collecting = False
        self.stop_cal_trigger = [False]
        self.set_active_components()
        
        self.cal_new_value = float('NaN')
        self.cal_pos_theta = 0.0
        self.cal_neg_theta = 0.0
        
        self.cal_window = PhaseOffsetCalibrationDialog(self)        
    
    def cal_start_record_thread(self,positive):
        self.cal_collecting = True
        self.stop_cal_trigger[0] = False
        self.set_active_components()
        self.cal_theta_thread = th.Thread(target=self.cal_record_thread,args=(positive,))
        self.cal_theta_thread.start() 

    def cal_record_thread(self,positive):
        self.log('Thread started...')
        self.lockin_daq_lock.acquire()
        avg = self.lockin_daq.read_ac_theta(self.stop_cal_trigger)
        self.lockin_daq_lock.release()
        
        if positive:
            self.cal_pos_theta = avg
        else:
            self.cal_neg_theta = avg
        self.log('Thread stopped...')
        
    def cal_get_current_values(self):
        return self.lockin_daq.ac_theta_avg,self.lockin_daq.ac_theta_count
    
    def cal_stop_record(self):
        if self.cal_collecting:
            self.stop_cal_trigger[0] = True
            self.cal_collecting = False
            self.set_active_components()
    
    def cal_get_new_phaseoffset(self,skipped_pos,skipped_neg):
        result = float('NaN')
        n = 0
        difference = 0
        if not skipped_pos:
            self.log('Positive theta at {:.3f} deg'.format(self.cal_pos_theta))
            difference += self.cal_pos_theta-90
            n += 1
        if not skipped_neg:
            self.log('Negative theta at {:.3f} deg'.format(self.cal_neg_theta))
            difference += self.cal_neg_theta+90
            n += 1
        if n>0:
            self.log('Change in phaseoffset: {:.3f} deg'.format(difference/n))
            result = self.lockin_daq.phaseoffset + difference/n
        self.cal_new_value = result
        return result
      
    def cal_apply_new(self):
        if not math.isnan(self.cal_new_value):
            self.set_phaseoffset(self.cal_new_value)
    
    def cal_end_after_thread(self):
        if not self.cal_theta_thread is None:
            if self.cal_theta_thread.is_alive():
                self.gui.window.after(100,self.cal_end_after_thread)
            else:
                self.cal_end()
        else:
            self.cal_end()    
    
    def cal_end(self):
        self.cal_collecting = False
        self.cal_running = False
        self.stop_cal_trigger[0] = False
        self.set_active_components()
        self.cal_window.window.destroy()
        
        self.log('')
        self.log('End of phase calibration.')
        
        #Save new calibration in last parameters file
        self.save_params('last')
        
    #---Phase offset calibration section end---


# In[46]:


ctr = Controller()

