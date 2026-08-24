from scripts.run_shadow import run_shadow

def test_shadow_runner_places_zero_orders(tmp_path):
    report=run_shadow(tmp_path/'shadow.sqlite3')
    assert report['status']=='SHADOW_ONLY'
    assert report['orders_placed']==0
    assert report['signed_calls']==0
