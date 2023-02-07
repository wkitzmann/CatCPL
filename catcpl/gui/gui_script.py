# CatCPL v1.0
# https://github.com/wkitzmann/CatCPL/
#
# Author: Winald R. Kitzmann
#
# CatCPL is distributed under the GNU General Public License 3.0 (https://www.gnu.org/licenses/gpl-3.0.html).
# 
# Main citation for CatCPL: XX
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# The user interface of CatCPL was created using TkDesigner by Parth Jadhav (https://github.com/ParthJadhav/Tkinter-Designer/) licensened under BSD 3-Clause "New" or "Revised" License (see /gui/tkdesigner_license).
# https://github.com/ParthJadhav/Tkinter-Designer


from pathlib import Path

# from tkinter import *
# Explicit imports to satisfy Flake8
from tkinter import Tk, Canvas, Entry, Text, Button, PhotoImage, ttk, IntVar, Checkbutton
from matplotlib.figure import Figure
from matplotlib import ticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import time
import numpy as np

class GUI():
    OUTPUT_PATH = Path(__file__).parent
    ASSETS_PATH = OUTPUT_PATH / Path("./assets")

    k = 0
        
    def get_state_const(self,b):
        if b:
            return 'normal'
        else:
            return 'disabled'

    def relative_to_assets(self,path: str) -> Path:
        return self.ASSETS_PATH / Path(path)

    def setup_all_plots(self):       
        self.osc_fig = Figure(figsize = (2.74,1.56),dpi = 100)
        self.osc_fig.set_facecolor("#FFFAD5")
        
        self.osc_ax = self.osc_fig.add_subplot(111)
        self.osc_ax.set_facecolor("#FFFDF1")
        self.osc_ax.set_ylabel('',fontsize=10)
        self.osc_canvas = FigureCanvasTkAgg(self.osc_fig,master = self.window) 
        self.osc_canvas.get_tk_widget().place(
            x=35.0,
            y=295.0,
            width=274.0,
            height=156.0
        )
        self.osc_fig.subplots_adjust(
            left=0.12,
            bottom=0.2, 
            right=0.985, 
            top=0.88, 
            wspace=0.0, 
            hspace=0.0)
        self.osc_canvas.draw()
        
        self.spec_fig = Figure(figsize = (2.74,6.76),dpi = 100)
        self.spec_fig.set_facecolor("#FFEDCC")
        self.total_ax = self.spec_fig.add_subplot(311)
        self.cpl_ax = self.spec_fig.add_subplot(312)
        self.glum_ax = self.spec_fig.add_subplot(313)
        self.total_ax.set_facecolor("#FFF9EF")
        self.cpl_ax.set_facecolor("#FFF9EF")
        self.glum_ax.set_facecolor("#FFF9EF")

        self.spec_canvas = FigureCanvasTkAgg(self.spec_fig,master = self.window) 
        self.spec_canvas.get_tk_widget().place(
            x=669.0,
            y=71.0,
            width=320.0,
            height=676.0
        )
        self.spec_fig.subplots_adjust(
            left=0.2,
            bottom=0.07, 
            right=0.95, 
            top=0.95, 
            wspace=0.0, 
            hspace=0.4)
        self.spec_canvas.draw()

    def plot(self,fig,canvas,ax,xlabel,ylabel,title,data,avgdata=[]):
        ax.clear()
        
        formatter = ticker.ScalarFormatter(useMathText=True)
        formatter.set_scientific(True) 
        formatter.set_powerlimits((0,0))        

        ax.set_xlabel(xlabel,fontsize=10)
        ax.set_ylabel(ylabel,fontsize=10)
        ax.set_title(title,fontsize=10)
        ax.yaxis.set_major_formatter(formatter)

        ax.plot(data[0], data[1])    
        
        if len(avgdata) > 0:
            if len(avgdata[0]) == len(avgdata[1]) and len(avgdata[0]) > 0:
                ax.plot(avgdata[0], avgdata[1])    

        if fig == self.osc_fig:
            fig.subplots_adjust(
                left=0.12,
                bottom=0.2, 
                right=0.985, 
                top=0.88, 
                wspace=0.0, 
                hspace=0.0)
            ax.set_facecolor("#FFFDF1")
            fig.set_facecolor("#FFFAD5")
        elif fig == self.spec_fig:
            fig.subplots_adjust(
                left=0.2,
                bottom=0.07, 
                right=0.95, 
                top=0.95, 
                wspace=0.0, 
                hspace=0.4) 
            ax.set_facecolor("#FFF9EF")
            fig.set_facecolor("#FFEDCC")
            ax.axhline(y=0.0, color="#0000004E", linestyle='-')
        canvas.draw()
        
    
    def plot_osc(self,data_max,max_len,time_step):
        self.plot(fig=self.osc_fig,canvas=self.osc_canvas,ax=self.osc_ax,data=[[-(min(max_len,data_max.size)-i)/(time_step/10) for i in range(0,data_max.size)], data_max],xlabel='',ylabel='',title='')
    
    def plot_spec(self,tot,tot_avg,cpl,cpl_avg,glum,glum_avg):
        s = 'Tot. Int.'
        if len(tot[1]) > 0:
            s = s + ' {:.1e} V'.format(tot[1][-1])   
        self.plot(self.spec_fig,self.spec_canvas,self.total_ax,'','',s,tot,tot_avg)
        
        s = 'CPL'
        if len(cpl[1]) > 0:
            s = s + ' {:.1e} V'.format(cpl[1][-1])           
        self.plot(self.spec_fig,self.spec_canvas,self.cpl_ax,'','',s,cpl,cpl_avg)
                
        s = 'glum'
        if len(glum[1]) > 0:
            s = s + ' {:.1e}'.format(glum[1][-1])   
        self.plot(self.spec_fig,self.spec_canvas,self.glum_ax,'WL / nm','',s,glum,glum_avg)    

    
    def set_spectra_setup_enable(self,b):
        self.edt_start['state'] = self.get_state_const(b)
        self.edt_end['state'] = self.get_state_const(b)
        self.edt_step['state'] = self.get_state_const(b)
        self.edt_dwell['state'] = self.get_state_const(b)
        self.edt_rep['state'] = self.get_state_const(b)
        self.edt_excSlit['state'] = self.get_state_const(b)
        self.edt_emSlit['state'] = self.get_state_const(b)
        self.edt_excWL['state'] = self.get_state_const(b)
        self.edt_comment['state'] = self.get_state_const(b)
        self.edt_filename['state'] = self.get_state_const(b)
        self.edt_ac_blank['state'] = self.get_state_const(b)
        self.edt_dc_blank['state'] = self.get_state_const(b)
        self.edt_det_corr['state'] = self.get_state_const(b)
        self.btn_start['state'] = self.get_state_const(b)
        self.btn_abort['state'] = self.get_state_const(b)
        self.chk_pem_off['state'] = self.get_state_const(b)          
    
    
    def set_signal_tuning_enable(self,b):
        self.edt_pmt['state'] = self.get_state_const(b)
        self.edt_gain['state'] = self.get_state_const(b)
        self.edt_WL['state'] = self.get_state_const(b)
        self.btn_set_PMT['state'] = self.get_state_const(b)
        self.btn_set_gain['state'] = self.get_state_const(b)
        self.btn_set_WL['state'] = self.get_state_const(b)
        self.btn_autorange['state'] = self.get_state_const(b)
        self.edt_phaseoffset['state'] = self.get_state_const(b)
        self.btn_set_phaseoffset['state'] = self.get_state_const(b)
        self.btn_cal_phaseoffset['state'] = self.get_state_const(b)
        if b:
            self.cbx_range['state'] = 'readonly'
        else:
            self.cbx_range['state'] = 'disabled'   

    
    def set_cat_visible(self,b):
        if b:
            self.canvas.itemconfig(self.img_cat, state='normal')
        else:
            self.canvas.itemconfig(self.img_cat, state='hidden')
    
    def __init__(self):
        self.window = Tk()
        self.window.title('CatCPL')
        #self.window.iconphoto(False, PhotoImage(file=self.relative_to_assets("icon2.png")))
        #self.window.tk.call('wm', 'iconphoto', self.window._w, PhotoImage(file=self.relative_to_assets("icon3.ico")))

        self.window.geometry("1330x785")
        self.window.configure(bg = "#E6EBFF")

        self.canvas = Canvas(
            self.window,
            bg = "#E6EBFF",
            height = 785,
            width = 1330,
            bd = 0,
            highlightthickness = 0,
            relief = "ridge"
        )
        self.canvas.place(x = 0, y = 0)
        
        #Setup plots
        self.setup_all_plots()
        
        #spectra setup
        self.canvas.create_rectangle(
            341.0,
            15.0,
            660.0,
            773.0,
            fill="#D1FFDB",
            outline="")
        
        #device setup
        self.canvas.create_rectangle(
            12.0,
            15.0,
            331.0,
            226.0,
            fill="#FFD5D5",
            outline="")
        
        #signal tuning
        self.canvas.create_rectangle(
            12.0,
            237.0,
            331.0,
            773.0,
            fill="#FFFAD5",
            outline="")

        #spectra
        self.canvas.create_rectangle(
            669.0,
            15.0,
            988.0,
            773.0,
            fill="#FFEDCC",
            outline="")
        #debug log
        self.canvas.create_rectangle(
            998.0,
            15.0,
            1317.0,
            773.0,
            fill="#D6CCFF",
            outline="")
        
        self.canvas.create_text(
            75.0,
            19.0,
            anchor="nw",
            text="Device Setup",
            fill="#000000",
            font=("Calibri", 32 * -1)
        )
        
        self.canvas.create_text(
            75.0,
            243.0,
            anchor="nw",
            text="Signal tuning",
            fill="#000000",
            font=("Calibri", 32 * -1)
        )

        self.canvas.create_text(
            34.0,
            458.0,
            anchor="nw",
            text="Peak  Voltage: ",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            34.0,
            510.0,
            anchor="nw",
            text="Avg.  Voltage: ",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.txt_maxVolt = self.canvas.create_text(
            169.0,
            458.0,
            anchor="nw",
            text="0 V",
            fill="#000000",
            font=("Calibri", 36 * -1)
        )
		
        self.txt_avgVolt = self.canvas.create_text(
            187.0,
            510.0,
            anchor="nw",
            text="0 V",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )
		
        self.txt_intensity = self.canvas.create_text(
            795.0,
            72.0,
            anchor="nw",
            text="0.0E+0",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )
        
        self.txt_CPL = self.canvas.create_text(
            795.0,
            299.0,
            anchor="nw",
            text="0.0E+0",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.txt_glum = self.canvas.create_text(
            795.0,
            513.0,
            anchor="nw",
            text="0.0E+0",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )	
        
        self.canvas.create_text(
            34.0,
            555.0,
            anchor="nw",
            text="PMT Input:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            35.0,
            129.0,
            anchor="nw",
            text="PEM:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.txt_PEM = self.canvas.create_text(
            137.0,
            129.0,
            anchor="nw",
            text="- nm",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            34.0,
            158.0,
            anchor="nw",
            text="Mono:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.txt_mono = self.canvas.create_text(
            136.0,
            158.0,
            anchor="nw",
            text="- nm",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            33.0,
            187.0,
            anchor="nw",
            text="MFLI:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.txt_mfli = self.canvas.create_text(
            135.0,
            187.0,
            anchor="nw",
            text="-",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            35.0,
            83.0,
            anchor="nw",
            text="Initialized:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.txt_init = self.canvas.create_text(
            137.0,
            83.0,
            anchor="nw",
            text="False",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            35.0,
            599.0,
            anchor="nw",
            text="Approx. gain:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            35.0,
            643.0,
            anchor="nw",
            text="Wavelength:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            35.0,
            580.0,
            anchor="nw",
            text="(rec. 0.5 - 1.1 V)",
            fill="#000000",
            font=("Calibri", 14 * -1)
        )

        self.canvas.create_text(
            34.0,
            625.0,
            anchor="nw",
            text="(rec. 0 - 885.6)",
            fill="#000000",
            font=("Calibri", 14 * -1)
        )
        
        self.canvas.create_text(
            35.0,
            687.0,
            anchor="nw",
            text="Range:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            399.0,
            19.0,
            anchor="nw",
            text="Spectra Setup",
            fill="#000000",
            font=("Calibri", 32 * -1)
        )

        self.canvas.create_text(
            772.0,
            19.0,
            anchor="nw",
            text="Spectra",
            fill="#000000",
            font=("Calibri", 32 * -1)
        )

        self.canvas.create_text(
            1080.0,
            19.0,
            anchor="nw",
            text="Debug Log",
            fill="#000000",
            font=("Calibri", 32 * -1)
        )
		
        self.photoimg_cat = PhotoImage(file=self.relative_to_assets("cat2.png"))
        self.img_cat = self.canvas.create_image(
            277.0,
            171.0,
            image=self.photoimg_cat
        )

        self.entry_image_1 = PhotoImage(
            file=self.relative_to_assets("entry_1.png"),master=self.window)
        self.entry_bg_1 = self.canvas.create_image(
            200.0,
            567.0,
            image=self.entry_image_1
        )
        
        self.edt_pmt = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_pmt.place(
            x=160.0,
            y=555.0,
            width=80.0,
            height=22.0
        )
        self.edt_pmt.insert(0,'0')

        self.canvas.create_text(
            363.0,
            83.0,
            anchor="nw",
            text="Start (nm):",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            116.0,
            anchor="nw",
            text="End (nm):",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            149.0,
            anchor="nw",
            text="Step size (nm):",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            182.0,
            anchor="nw",
            text="Dwell Time (s):",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            215.0,
            anchor="nw",
            text="Repetitions:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            279.0,
            anchor="nw",
            text="Exc. Slit (mm):",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            312.0,
            anchor="nw",
            text="Em. Slit (mm):",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            345.0,
            anchor="nw",
            text="Exc. WL (nm):",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            378.0,
            anchor="nw",
            text="Comment:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            442.0,
            anchor="nw",
            text="Filename:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            731.0,
            anchor="nw",
            text="Progress:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.txt_progress = self.canvas.create_text(
            448.0,
            731.0,
            anchor="nw",
            text="0 %",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.canvas.create_text(
            363.0,
            481.0,
            anchor="nw",
            text="AC-Blank File:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )
        
        self.canvas.create_text(
            363.0,
            561.0,
            anchor="nw",
            text="DC-Blank File:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )
        
        self.canvas.create_text(
            363.0,
            601.0,
            anchor="nw",
            text="Det. correction:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )        

        self.entry_image_2 = PhotoImage(
            file=self.relative_to_assets("entry_2.png"),master=self.window)
        self.entry_bg_2 = self.canvas.create_image(
            569.0,
            96.0,
            image=self.entry_image_2
        )
        self.edt_start = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_start.place(
            x=500.0,
            y=84.0,
            width=138.0,
            height=22.0
        )
        self.edt_start.insert(0,'800')

        self.entry_image_3 = PhotoImage(
            file=self.relative_to_assets("entry_3.png"),master=self.window)
        self.entry_bg_3 = self.canvas.create_image(
            569.0,
            129.0,
            image=self.entry_image_3
        )
        self.edt_end = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_end.place(
            x=500.0,
            y=117.0,
            width=138.0,
            height=22.0
        )
        self.edt_end.insert(0,'200')

        self.entry_image_4 = PhotoImage(
            file=self.relative_to_assets("entry_4.png"),master=self.window)
        self.entry_bg_4 = self.canvas.create_image(
            569.0,
            162.0,
            image=self.entry_image_4
        )
        self.edt_step = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_step.place(
            x=500.0,
            y=150.0,
            width=138.0,
            height=22.0
        )
        self.edt_step.insert(0,'1')

        self.entry_image_5 = PhotoImage(
            file=self.relative_to_assets("entry_5.png"),master=self.window)
        self.entry_bg_5 = self.canvas.create_image(
            569.0,
            195.0,
            image=self.entry_image_5
        )
        self.edt_dwell = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_dwell.place(
            x=500.0,
            y=183.0,
            width=138.0,
            height=22.0
        )
        self.edt_dwell.insert(0,'0.5')

        self.entry_image_6 = PhotoImage(
            file=self.relative_to_assets("entry_6.png"),master=self.window)
        self.entry_bg_6 = self.canvas.create_image(
            569.0,
            228.0,
            image=self.entry_image_6
        )
        self.edt_rep = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_rep.place(
            x=500.0,
            y=216.0,
            width=138.0,
            height=22.0
        )
        self.edt_rep.insert(0,'1')

        self.entry_image_7 = PhotoImage(
            file=self.relative_to_assets("entry_7.png"),master=self.window)
        self.entry_bg_7 = self.canvas.create_image(
            569.0,
            292.0,
            image=self.entry_image_7
        )
        self.edt_excSlit = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_excSlit.place(
            x=500.0,
            y=280.0,
            width=138.0,
            height=22.0
        )

        self.entry_image_8 = PhotoImage(
            file=self.relative_to_assets("entry_8.png"),master=self.window)
        self.entry_bg_8 = self.canvas.create_image(
            569.0,
            325.0,
            image=self.entry_image_8
        )
        self.edt_emSlit = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_emSlit.place(
            x=500.0,
            y=313.0,
            width=138.0,
            height=22.0
        )

        self.entry_image_9 = PhotoImage(
            file=self.relative_to_assets("entry_9.png"),master=self.window)
        self.entry_bg_9 = self.canvas.create_image(
            569.0,
            358.0,
            image=self.entry_image_9
        )
        self.edt_excWL = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_excWL.place(
            x=500.0,
            y=346.0,
            width=138.0,
            height=22.0
        )
        self.edt_excWL.insert(0,'365')

        self.entry_image_10 = PhotoImage(
            file=self.relative_to_assets("entry_10.png"),master=self.window)
        self.entry_bg_10 = self.canvas.create_image(
            569.0,
            391.0,
            image=self.entry_image_10
        )
        self.edt_comment = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_comment.place(
            x=500.0,
            y=379.0,
            width=138.0,
            height=22.0
        )

        self.entry_image_11 = PhotoImage(
            file=self.relative_to_assets("entry_11.png"),master=self.window)
        self.entry_bg_11 = self.canvas.create_image(
            569.0,
            455.0,
            image=self.entry_image_11
        )
        self.edt_filename = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_filename.place(
            x=500.0,
            y=443.0,
            width=138.0,
            height=22.0
        )
        self.edt_filename.insert(0,'spec01')
		
        self.entry_image_20 = PhotoImage(file=self.relative_to_assets("entry_20.png"))
        self.entry_bg_20 = self.canvas.create_image(
            569.0,
            455.0,
            image=self.entry_image_20
        )
        self.edt_ac_blank = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_ac_blank.place(
            x=500.0,
            y=482.0,
            width=138.0,
            height=22.0
        )
		
        self.var_pem_off = IntVar()
        self.chk_pem_off = Checkbutton(
            self.window,
            text='PEM off',
            variable=self.var_pem_off,
            onvalue=1,
            offvalue=0,
            font=("Calibri", 20 * -1),
            bg="#D1FFDB"
        )
        self.chk_pem_off.place(
            x=480.0,
            y=521.0,
            width=150.0,
            height=22.0
        )
        
        self.entry_image_60 = PhotoImage(file=self.relative_to_assets("entry_20.png"))
        self.entry_bg_60 = self.canvas.create_image(
            569.0,
            573.0,
            image=self.entry_image_60
        )
        self.edt_dc_blank = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_dc_blank.place(
            x=500.0,
            y=561.0,
            width=138.0,
            height=22.0
        )
        
        self.entry_image_61 = PhotoImage(file=self.relative_to_assets("entry_20.png"))
        self.entry_bg_61 = self.canvas.create_image(
            569.0,
            613.0,
            image=self.entry_image_61
        )
        self.edt_det_corr = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_det_corr.place(
            x=500.0,
            y=601.0,
            width=138.0,
            height=22.0
        )


        self.entry_image_12 = PhotoImage(
        file=self.relative_to_assets("entry_12.png"),master=self.window)
        self.entry_bg_12 = self.canvas.create_image(
            1158.0,
            361.5,
            image=self.entry_image_12
        )
        self.edt_debuglog = Text(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0,
            font=("Calibri", 10)
        )
        self.edt_debuglog.place(
            x=1030.0,
            y=75.0,
            width=256.0,
            height=666.0
        )

        self.entry_image_13 = PhotoImage(
            file=self.relative_to_assets("entry_13.png"),master=self.window)
        self.entry_bg_13 = self.canvas.create_image(
            200.0,
            655.0,
            image=self.entry_image_13
        )
        self.edt_WL = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_WL.place(
            x=160.0,
            y=643.0,
            width=80.0,
            height=22.0
        )
        
        self.entry_image_23 = PhotoImage(
            file=self.relative_to_assets("entry_40.png"),master=self.window)
        self.entry_bg_13 = self.canvas.create_image(
            187.5,
            743.0,
            image=self.entry_image_23
        )
        self.edt_phaseoffset = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_phaseoffset.place(
            x=160.0,
            y=731.0,
            width=55.0,
            height=22.0
        )

        self.entry_image_14 = PhotoImage(
            file=self.relative_to_assets("entry_14.png"),master=self.window)
        self.entry_bg_14 = self.canvas.create_image(
            200.0,
            611.0,
            image=self.entry_image_14
        )
        self.edt_gain = Entry(
            bd=0,
            bg="#FFFFFF",
            highlightthickness=0
        )
        self.edt_gain.place(
            x=160.0,
            y=599.0,
            width=80.0,
            height=22.0
        )
        self.edt_gain.insert(0,'0')

        self.button_image_1 = PhotoImage(
            file=self.relative_to_assets("button_1.png"),master=self.window)
        self.btn_init = Button(
            image=self.button_image_1,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_1 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_init.place(
            x=224.0,
            y=71.0,
            width=84.0,
            height=24.0
        )

        self.btn_close_img = PhotoImage(
            file=self.relative_to_assets("button_close.png"),master=self.window)
        self.btn_close = Button(
            image=self.btn_close_img,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_2 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_close.place(
            x=224.0,
            y=95.0,
            width=84.0,
            height=24.0
        )

        self.button_image_2 = PhotoImage(
            file=self.relative_to_assets("button_2.png"),master=self.window)
        self.btn_set_PMT = Button(
            image=self.button_image_2,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_2 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_set_PMT.place(
            x=258.0,
            y=555.0,
            width=50.0,
            height=24.0
        )

        self.button_image_3 = PhotoImage(
            file=self.relative_to_assets("button_2.png"),master=self.window)
        self.btn_set_gain = Button(
            image=self.button_image_3,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_3 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_set_gain.place(
            x=258.0,
            y=599.0,
            width=50.0,
            height=24.0
        )

        self.button_image_4 = PhotoImage(
            file=self.relative_to_assets("button_2.png"),master=self.window)
        self.btn_set_WL = Button(
            image=self.button_image_4,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_4 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_set_WL.place(
            x=258.0,
            y=643.0,
            width=50.0,
            height=24.0
        )
        
        self.cbx_range = ttk.Combobox(
            master=self.window)
        self.cbx_range.place(
            x=160.0,
            y=687.0,
            width=80.0,
            height=24.0
        )    
        self.cbx_range['values'] = ('0.003','0.010','0.030','0.100','0.300','1.000','3.000')
        self.cbx_range['state'] = 'readonly'
        self.cbx_range.set('3.000')
            
        
        self.button_image_auto = PhotoImage(
            file=self.relative_to_assets("auto.png"),master=self.window)
        self.btn_autorange = Button(
            image=self.button_image_auto,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_4 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_autorange.place(
            x=258.0,
            y=687.0,
            width=50.0,
            height=24.0
        )

        self.canvas.create_text(
            35.0,
            731.0,
            anchor="nw",
            text="Phase offset:",
            fill="#000000",
            font=("Calibri", 20 * -1)
        )

        self.button_image_40 = PhotoImage(
            file=self.relative_to_assets("button_po_set.png"),master=self.window)
        self.btn_set_phaseoffset = Button(
            image=self.button_image_40,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_4 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_set_phaseoffset.place(
            x=230.0,
            y=731.0,
            width=36.0,
            height=24.0
        )

        self.button_image_41 = PhotoImage(
            file=self.relative_to_assets("button_po_cal.png"),master=self.window)
        self.btn_cal_phaseoffset = Button(
            image=self.button_image_41,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_4 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_cal_phaseoffset.place(
            x=272.0,
            y=731.0,
            width=36.0,
            height=24.0
        )

        self.button_image_5 = PhotoImage(
            file=self.relative_to_assets("button_5.png"),master=self.window)
        self.btn_start = Button(
            image=self.button_image_5,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_5 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_start.place(
            x=363.0,
            y=668.0,
            width=125.0,
            height=53.0
        )

        self.button_image_6 = PhotoImage(
            file=self.relative_to_assets("button_6.png"),master=self.window)
        self.btn_abort = Button(
            image=self.button_image_6,
            borderwidth=0,
            highlightthickness=0,
            command=lambda: print("button_6 clicked"),
            master=self.window,
            relief="flat"
        )
        self.btn_abort.place(
            x=513.0,
            y=668.0,
            width=125.0,
            height=53.0
        )
        self.window.resizable(False, False)
        