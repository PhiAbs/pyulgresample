import pandas as pd
import numpy as np
import argparse
import os
import pyulog
from pyulgresample import ulogconv as conv
from pyulgresample import mathpandas as mpd
from pyulgresample import plotwrapper as pltw
from pyulgresample import loginfo
from pyulgresample import dfUlg

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

parser = argparse.ArgumentParser(description="Script to process attitude")
parser.add_argument("filename", metavar="file.ulg", help="ulog file")


class dfUlgAttitude(dfUlg.dfUlgBase):
    """
    dfUlgBase-Childclass for attitude and attitude-septoint topic
    """

    @classmethod
    def get_required_topics(self):
        """
        Returns:
            List of required topics
        """
        return ["vehicle_attitude", "vehicle_attitude_setpoint"]

    @classmethod
    def get_required_zoh_topics(self):
        """
        Returns:
            List of topics on which zoh is applied
        """
        return []

    @classmethod
    def get_nan_topic_msgs(self):
        """
        Returns:
            list of TopicMsgs
        """
        return []


def add_roll_pitch_yaw(df):
    roll, pitch, yaw = mpd.series_quat2euler(
        df["T_vehicle_attitude_0__F_q_0"],
        df["T_vehicle_attitude_0__F_q_1"],
        df["T_vehicle_attitude_0__F_q_2"],
        df["T_vehicle_attitude_0__F_q_3"],
    )
    df["T_vehicle_attitude_0__NF_roll"] = roll.values
    df["T_vehicle_attitude_0__NF_pitch"] = pitch.values
    df["T_vehicle_attitude_0__NF_yaw"] = yaw.values


def add_euler_error(df):
    df["T_vehicle_attitude_setpoint_0__NF_e_roll"] = mpd.angle_wrap(
        df["T_vehicle_attitude_setpoint_0__F_roll_body"]
        - df["T_vehicle_attitude_0__NF_roll"]
    )
    df["T_vehicle_attitude_setpoint_0__NF_e_pitch"] = mpd.angle_wrap(
        df["T_vehicle_attitude_setpoint_0__F_pitch_body"]
        - df["T_vehicle_attitude_0__NF_pitch"]
    )
    df["T_vehicle_attitude_setpoint_0__NF_e_yaw"] = mpd.angle_wrap(
        df["T_vehicle_attitude_setpoint_0__F_yaw_body"]
        - df["T_vehicle_attitude_0__NF_yaw"]
    )


def add_vehicle_z_axis(df):
    x = pd.Series(
        np.zeros(df.shape[0]),
        index=df["timestamp"],
        name="T_vehicle_attitude_0__NF_body_z_axis_x",
    )
    y = pd.Series(
        np.zeros(df.shape[0]),
        index=df["timestamp"],
        name="T_vehicle_attitude_0__NF_body_z_axis_y",
    )
    z = pd.Series(
        np.ones(df.shape[0]),
        index=df["timestamp"],
        name="T_vehicle_attitude_0__NF_body_z_axis_z",
    )
    x, y, z = mpd.series_quatrot(
        x,
        y,
        z,
        df["T_vehicle_attitude_0__F_q_0"],
        df["T_vehicle_attitude_0__F_q_1"],
        df["T_vehicle_attitude_0__F_q_2"],
        df["T_vehicle_attitude_0__F_q_3"],
    )

    df[x.name] = x.values
    df[y.name] = y.values
    df[z.name] = z.values


def add_desired_tilt(df):

    if "T_vehicle_attitude_setpoint_0__NF_body_z_axis_sp_x" not in df:
        add_desired_z_axis(df)

    x = pd.Series(np.zeros(df.shape[0]), index=df["timestamp"], name="x")
    y = pd.Series(np.zeros(df.shape[0]), index=df["timestamp"], name="y")
    z = pd.Series(np.ones(df.shape[0]), index=df["timestamp"], name="z")

    tilt = mpd.series_dot(
        x,
        y,
        z,
        df["T_vehicle_attitude_setpoint_0__NF_body_z_axis_sp_x"],
        df["T_vehicle_attitude_setpoint_0__NF_body_z_axis_sp_y"],
        df["T_vehicle_attitude_setpoint_0__NF_body_z_axis_sp_z"],
    )
    tilt.where(
        tilt < 1, 1, inplace=True
    )  # ensure that angle 1 is never exceeded
    df["T_vehicle_attitude_setpoint_0__NF_tilt_desired"] = tilt.values
    df["T_vehicle_attitude_setpoint_0__NF_tilt_desired"] = df[
        "T_vehicle_attitude_setpoint_0__NF_tilt_desired"
    ].apply(np.arccos)


def add_tilt(df):

    if "T_vehicle_attitude_0__NF_body_z_axis_x" not in df:
        add_vehicle_z_axis(df)

    x = pd.Series(np.zeros(df.shape[0]), index=df["timestamp"], name="x")
    y = pd.Series(np.zeros(df.shape[0]), index=df["timestamp"], name="y")
    z = pd.Series(np.ones(df.shape[0]), index=df["timestamp"], name="z")

    tilt = mpd.series_dot(
        x,
        y,
        z,
        df["T_vehicle_attitude_0__NF_body_z_axis_x"],
        df["T_vehicle_attitude_0__NF_body_z_axis_y"],
        df["T_vehicle_attitude_0__NF_body_z_axis_z"],
    )
    tilt.where(
        tilt < 1, 1, inplace=True
    )  # ensure that angle 1 is never exceeded
    df["T_vehicle_attitude_0__NF_tilt"] = tilt.values
    df["T_vehicle_attitude_0__NF_tilt"] = df[
        "T_vehicle_attitude_0__NF_tilt"
    ].apply(np.arccos)


def add_vehicle_inverted(df):

    if "T_vehicle_attitude_0__NF_body_z_axis_z" not in df:
        add_vehicle_z_axis(df)

    df[
        "T_vehicle_attitude_0__NF_tilt_more_90"
    ] = df.T_vehicle_attitude_0__NF_body_z_axis_z.values
    df[df[["T_vehicle_attitude_0__NF_tilt_more_90"]] >= 0] = 0
    df[df[["T_vehicle_attitude_0__NF_tilt_more_90"]] < 0] = 1


def add_desired_z_axis(df):
    x = pd.Series(
        np.zeros(df.shape[0]),
        index=df["timestamp"],
        name="T_vehicle_attitude_setpoint_0__NF_body_z_axis_sp_x",
    )
    y = pd.Series(
        np.zeros(df.shape[0]),
        index=df["timestamp"],
        name="T_vehicle_attitude_setpoint_0__NF_body_z_axis_sp_y",
    )
    z = pd.Series(
        np.ones(df.shape[0]),
        index=df["timestamp"],
        name="T_vehicle_attitude_setpoint_0__NF_body_z_axis_sp_z",
    )

    x, y, z = mpd.series_quatrot(
        x,
        y,
        z,
        df["T_vehicle_attitude_setpoint_0__F_q_d_0"],
        df["T_vehicle_attitude_setpoint_0__F_q_d_1"],
        df["T_vehicle_attitude_setpoint_0__F_q_d_2"],
        df["T_vehicle_attitude_setpoint_0__F_q_d_3"],
    )
    df[x.name] = x.values
    df[y.name] = y.values
    df[z.name] = z.values


def main():
    args = parser.parse_args()
    # create dataframe-ulog class for Attitude/Attiutde-setpoint topic
    att = dfUlgAttitude.create(args.filename)

    with PdfPages("px4_attitude.pdf") as pdf:

        # roll pitch and yaw error
        add_roll_pitch_yaw(att.df)
        add_euler_error(att.df)

        plt.figure(0, figsize=(20, 13))
        df_tmp = att.df[
            [
                "timestamp",
                "T_vehicle_attitude_setpoint_0__NF_e_roll",
                "T_vehicle_attitude_setpoint_0__NF_e_pitch",
                "T_vehicle_attitude_setpoint_0__NF_e_yaw",
            ]
        ].copy()
        df_tmp.plot(x="timestamp", linewidth=0.8)
        pltw.plot_time_series(df_tmp, plt)
        plt.title("Roll-Pitch-Yaw-Error")
        plt.ylabel("rad")
        pdf.savefig()
        plt.close(0)

        # inverted
        add_vehicle_z_axis(att.df)
        add_vehicle_inverted(att.df)
        plt.figure(1, figsize=(20, 13))
        df_tmp = att.df[
            ["timestamp", "T_vehicle_attitude_0__NF_tilt_more_90"]
        ].copy()
        df_tmp.plot(x="timestamp", linewidth=0.8)
        pltw.plot_time_series(df_tmp, plt)
        plt.title("Inverted")
        plt.ylabel("boolean")
        pdf.savefig()
        plt.close(1)

        # tilt and desired tilt
        add_desired_z_axis(att.df)
        add_desired_tilt(att.df)
        add_tilt(att.df)

        pos_tilt = loginfo.get_param(att.ulog, "MPC_TILTMAX_AIR", 0)
        man_tilt = loginfo.get_param(att.ulog, "MPC_MAN_TILT_MAX", 0)
        plt.figure(2, figsize=(20, 13))
        df_tmp = att.df[
            [
                "timestamp",
                "T_vehicle_attitude_0__NF_tilt",
                "T_vehicle_attitude_setpoint_0__NF_tilt_desired",
            ]
        ].copy()
        df_tmp["MPC_TILTMAX_AIR"] = pos_tilt * np.pi / 180
        df_tmp["MPC_MAN_TILT_MAX"] = man_tilt * np.pi / 180
        df_tmp.plot(x="timestamp", linewidth=0.8, style=["-", "-", "--", "--"])

        pltw.plot_time_series(df_tmp, plt)
        plt.title("Tilt / Desired Tilt")
        plt.ylabel("rad")
        pdf.savefig()
        plt.close(2)

        print("px4_attitude.pdf was created")
