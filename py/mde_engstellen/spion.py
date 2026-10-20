"""Fuehrt ein Skript aus und meldet bei jedem resample('1h') den Stempelfehler der Reihe."""
import sys, runpy, pandas as pd
sys.path.insert(0, '/home/oliver/weather/py')
import cmems_stroemung_nachholen as C
_orig = pd.DataFrame.resample
def spion(self, rule, *a, **k):
    if str(rule).lower() == '1h' and isinstance(self.index, pd.DatetimeIndex) and len(self):
        print('  RESAMPLE delta %.2f min n=%d' % (C.stempelfehler_min(self.index), len(self)), flush=True)
    return _orig(self, rule, *a, **k)
pd.DataFrame.resample = spion
skript = sys.argv[1]; sys.argv = sys.argv[1:]
runpy.run_path(skript, run_name='__main__')
