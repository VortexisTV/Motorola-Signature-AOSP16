package vantage.telephony.rilready;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Nothing to do: delivering the broadcast creates the process, and RilReadyApp does the work. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
    }
}
