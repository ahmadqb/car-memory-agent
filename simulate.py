"""python simulate.py  -> resets the memory DB, replays 14 days of signals, prints the learned profile."""
import memory
from signals import generate_events

USER = "driver1"

if __name__ == "__main__":
    memory.init_db(reset=True)
    for ts, signal, value in generate_events():
        memory.add_observation(USER, signal, value, ts, derive=False)
    memory.derive_facts(USER)
    print(f"Learned profile for {USER}:")
    for f in memory.get_profile(USER):
        print(f"  {f['key']:<28} = {f['value']:<11} confidence {f['confidence']:.2f} (last {f['support']} obs)")
