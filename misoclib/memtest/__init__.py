from migen.fhdl.std import *
from migen.genlib.misc import optree
from migen.bank.description import *
from migen.actorlib import dma_lasmi
from migen.actorlib.spi import *

@DecorateModule(InsertReset)
@DecorateModule(InsertCE)
class LFSR(Module):
	def __init__(self, n_out, n_state=31, taps=[27, 30]):
		self.o = Signal(n_out)

		###

		state = Signal(n_state)
		curval = [state[i] for i in range(n_state)]
		curval += [0]*(n_out - n_state)
		for i in range(n_out):
			nv = ~optree("^", [curval[tap] for tap in taps])
			curval.insert(0, nv)
			curval.pop()

		self.sync += [
			state.eq(Cat(*curval[:n_state])),
			self.o.eq(Cat(*curval))
		]

memtest_magic = 0x361f

class MemtestWriter(Module):
	def __init__(self, lasmim):
		self._r_magic = CSRStatus(16)
		self._r_reset = CSR()
		self._r_shoot = CSR()
		self.submodules._dma = DMAWriteController(dma_lasmi.Writer(lasmim), MODE_EXTERNAL)

		###

		self.comb += self._r_magic.status.eq(memtest_magic)

		lfsr = LFSR(lasmim.dw)
		self.submodules += lfsr
		self.comb += lfsr.reset.eq(self._r_reset.re)

		en = Signal()
		en_counter = Signal(lasmim.aw)
		self.comb += en.eq(en_counter != 0)
		self.sync += [
			If(self._r_shoot.re,
				en_counter.eq(self._dma.length)
			).Elif(lfsr.ce,
				en_counter.eq(en_counter - 1)
			)
		]

		self.comb += [
			self._dma.trigger.eq(self._r_shoot.re),
			self._dma.data.stb.eq(en),
			lfsr.ce.eq(en & self._dma.data.ack),
			self._dma.data.payload.d.eq(lfsr.o)
		]

	def get_csrs(self):
		return [self._r_magic, self._r_reset, self._r_shoot] + self._dma.get_csrs()

class MemtestReader(Module):
	def __init__(self, lasmim):
		self._r_magic = CSRStatus(16)
		self._r_reset = CSR()
		self._r_error_count = CSRStatus(lasmim.aw)
		self.submodules._dma = DMAReadController(dma_lasmi.Reader(lasmim), MODE_SINGLE_SHOT)

		###

		self.comb += self._r_magic.status.eq(memtest_magic)

		lfsr = LFSR(lasmim.dw)
		self.submodules += lfsr
		self.comb += lfsr.reset.eq(self._r_reset.re)

		self.comb += [
			lfsr.ce.eq(self._dma.data.stb),
			self._dma.data.ack.eq(1)
		]
		err_cnt = self._r_error_count.status
		self.sync += [
			If(self._r_reset.re,
				err_cnt.eq(0)
			).Elif(self._dma.data.stb,
				If(self._dma.data.payload.d != lfsr.o, err_cnt.eq(err_cnt + 1))
			)
		]

	def get_csrs(self):
		return [self._r_magic, self._r_reset, self._r_error_count] + self._dma.get_csrs()

class _LFSRTB(Module):
	def __init__(self, *args, **kwargs):
		self.submodules.dut = LFSR(*args, **kwargs)
		self.comb += self.dut.ce.eq(1)

	def do_simulation(self, selfp):
		print("{0:032x}".format(selfp.dut.o))

if __name__ == "__main__":
	from migen.fhdl import verilog
	from migen.sim.generic import run_simulation

	lfsr = LFSR(3, 4, [3, 2])
	print(verilog.convert(lfsr, ios={lfsr.ce, lfsr.reset, lfsr.o}))

	run_simulation(_LFSRTB(128), ncycles=20)
