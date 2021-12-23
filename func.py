import pandas as pd
import datetime
import os
from difflib import SequenceMatcher


class Initial_Log():
    """
    Prepare log for calculation
    
    Parameters
    -----------
    DataFrame: (pandas.DataFrame) - initial log
    col_identifier_name: (str)
    col_events_name: (str)
    col_time_name: (str)
    timeformat: (str) - example: "%Y-%m-%d %H:%M:%S"
    
    Returns
    -----------
    df:
    
    """
    
    def __init__(self, DataFrame, col_identifier_name, col_events_name, col_time_name, timeformat = None):
        
        self.df = DataFrame[[col_identifier_name, col_events_name, col_time_name]].copy()
        self.id_colname = col_identifier_name
        self.events_colname = col_events_name
        self.time_colname = col_time_name
        self.next_event_colname = "next_event"
        self.next_time_colname = "next_time"
        self.t_format = timeformat
        
        if self.t_format is not None:
            self.df[self.time_colname] = pd.to_datetime(self.df[self.time_colname], format=self.t_format)
        else:
            self.df[self.time_colname] = pd.to_datetime(self.df[self.time_colname], infer_datetime_format=True)
            
        self._sort_log_by_time()
        self._shift_process_col()
        self._shift_time_col()
            
        
    def _sort_log_by_time(self):
        """
        Sort data by identifier and time
        """
        self.df.set_index([self.id_colname, self.time_colname]).sort_index(inplace=True)
        self.df.reset_index(inplace=True)
    
    def _shift_process_col(self):
        """
        Get column of next events for each step by identifier
        """
        self.df[self.next_event_colname] = self.df.groupby(self.id_colname)[self.events_colname]\
                                                  .shift(periods=-1, fill_value="Log End")
    
    def _shift_time_col(self):
        """
        Get column of next time for each step by identifier
        """
        self.df[self.next_time_colname] = self.df.groupby(self.id_colname)[self.time_colname]\
                                                 .shift(periods=-1)
        self.df.at[self.df[self.df[self.next_time_colname].isnull()].index, self.next_time_colname] =\
                         self.df[self.df[self.next_time_colname].isnull()][self.time_colname]
    
    @staticmethod
    def join_events(vals):
        """
        Concat of list events in union string
        """
        return "-|>".join([i for i in vals])   

    
    def get_top_chain_sequences(self, seq_count_tresh = 10):
        """
        This function define most popular chain sequences in log
        Parameters
        -----------
        seq_count_tresh: (int) - how many chain of sequences will return 
        Returns
        -----------
            df_seq: (DataFrame) - top sequences of process events
        """
        temp_df = self.df.groupby(self.id_colname).agg({self.events_colname: self.join_events})

        data = []
        for c, itms in enumerate(dict(temp_df[self.events_colname].value_counts()).items()):
            if c < seq_count_tresh:
                for i, s in enumerate(itms[0].split("-|>")):
                    data.append([c+1, itms[1], i+1, s])
            else:
                break
        temp_df = pd.DataFrame(data, columns=["ChainNumber", 
                                             "ChainFrequency", 
                                             "StepNumberOfChain", 
                                             "EventName"])
        temp_df.sort_values(by=["ChainNumber", "StepNumberOfChain"], inplace=True)

        return temp_df
    
        
    def get_frame(self):
        """
        Get dataframe with next time and events for each step by identifier
        """
        return self.df
    
    
    
class Optimal_Process():
    
    def __init__(self, Initial_Log):
        self.base_df = Initial_Log.df
        self.id_col = Initial_Log.id_colname
        self.event_col = Initial_Log.events_colname
        self.time_col = Initial_Log.time_colname
        self.next_event_col = Initial_Log.next_event_colname
        self.next_time_col = Initial_Log.next_time_colname
        self.sequences_df = None
        self.sequences_similarity = None
        self.sequences_counts_ratio = None

        self.__get_sequences_df()
    
    @staticmethod
    def join_events(vals):
        return "-|>".join([i for i in vals])
    
    @staticmethod
    def convert_to_timedelta(sec):
        return str(datetime.timedelta(seconds=sec))
    
    @staticmethod
    def similar(a, b):
        return SequenceMatcher(None, a, b).ratio()
    
    @staticmethod
    def sort_dict_by_value(d, revers):
        return dict(sorted(d.items(), key=lambda x: x[1], reverse=revers))
    
    def get_time_diff_between_events(self, events_all_log, events_from_seq):
        """
        This function calculating diff time of events from different dataframe
        Parameters
        -----------
        events_all_log: (dict) - events time duration in sec for all log
        events_from_seq: (dict) - events time duration in sec for choisen sequence
        Returns
        -----------
        stat: (dict) - 
        """
        stat = dict()
        for k in events_from_seq.keys():
            stat[k] = self.convert_to_timedelta(events_from_seq.get(k) - events_all_log.get(k))
        return stat
       
    def __check_concurrency_start_end_events(self, choisen, dict_for_compare, reverse = False):
        """
        This function compare start and end events between choisen sequence and sequence from all log
        Parameters
        -----------
        choisen: (str) - choisen sequence with '-|>' separator between events
        dict_for_compare: (dict) - sequence from all log with time duration in value
        reverse: (bool) - how sort dict by value (default ascending)
        Returns
        -----------
        (dict) - filtered dict_for_compare of sequence with start - end events from choisen
        """
        st_ch = choisen.split("-|>")[0]
        end_ch = choisen.split("-|>")[-1]
        new_dict = dict()
        for k,v in dict_for_compare.items():
            st_cmp = k.split("-|>")[0]
            end_cmp = k.split("-|>")[-1]
            if (st_ch == st_cmp) & (end_ch == end_cmp):
                new_dict[k] = v
        if len(new_dict) != 0:
            return self.sort_dict_by_value(new_dict, reverse)
        return dict()
    
    def get_start_end_seq_in_log(self):
        """
        This function return combinations of start_event --> end_event from all log
        Parameters
        -----------
        Returns
        -----------
        """
        f = self.base_df.groupby(self.id_col)[self.event_col].first().reset_index()
        f["last"] = f[self.id_col].map(self.base_df.groupby(self.id_col)[self.event_col].last())
        dd = dict(f.value_counts([self.event_col, "last"]))
        for k,v in dd.items():
            print("-*"*20)
            print(f"'{k[0]}' --> '{k[1]}': {v} times")

    def __get_sequences_df(self):
        """
        This function define unique sequences from all log and calculating time duration of each sequences (in seconds)
        Parameters
        -----------
        base_df: (DataFrame) - df from full log
        Returns (self)
        -----------
        sequences_df: (DataFrame)
        """
        self.sequences_df = self.base_df.groupby(self.id_col).agg({self.event_col: self.join_events}).reset_index()
        time_delta = self.base_df.groupby(self.id_col)[self.time_col].last() -\
                     self.base_df.groupby(self.id_col)[self.time_col].first()
        self.sequences_df["time_delta"] = (self.sequences_df[self.id_col].map(time_delta)).dt.total_seconds()
    
    def __get_transact_medtime(self, df):
        """
        This function define median time duration for each transition
        Parameters
        -----------
        base_df: (DataFrame) - df with time and next_time columns
        Returns 
        -----------
        (dict) - median time duration for each pairs (event_1 -|> event_2, ....)
        """
        if df.shape[0] == 0:
            return {}
        df["diff_time"] = (df[self.next_time_col] -\
                                           df[self.time_col]).dt.total_seconds()
        return dict(df.groupby([self.event_col, self.next_event_col])\
                       ["diff_time"].median())
    
    def get_id_by_sequence(self, sequence):
        if type(sequence) == str:
            return self.sequences_df[self.sequences_df[self.event_col] == sequence][self.id_col].unique()
        elif type(sequence) == list:
            str_sequence = join_events(sequence)
            return self.sequences_df[self.sequences_df[self.event_col] == str_sequence][self.id_col].unique()
        else:
            print("Sequence not found, please, check the entered sequence for correctness")
            return []
    
    def __get_df_by_id(self, sequence):
        ids = self.get_id_by_sequence(sequence)
        if len(ids) == 0:
            return pd.DataFrame()
        return self.base_df[self.base_df[self.id_col].isin(ids)]
    
    def __get_sequences_medtime(self):    
        return dict(self.sequences_df.groupby(self.event_col)["time_delta"].median())

    def __get_seq_similarity(self, choisen_seq):
        """
        This function define similarity measure between choisen sequence and sequences from all log
        Parameters
        -----------
        choisen_seq: (str) - 'event_1-|>event_2-|>event_3....'
        Returns 
        -----------
        (dict) - with similarity measure for all sequences
        """
        self.sequences_similarity = dict()
        seqns = self.sequences_df[self.event_col].unique()
        for seq in seqns:
            self.sequences_similarity[seq] = self.similar(seq, choisen_seq)
            
    def __get_seq_counts_ratio(self):
        """
        Get counts by sequences from log
        """
        count_uniq_id = self.sequences_df[self.event_col].unique().shape[0]
        counts_seq_d = dict(self.sequences_df[self.event_col].value_counts())
        self.sequences_counts_ratio = self.sort_dict_by_value(counts_seq_d, True)
    
    def __select_best_sequence(self, med_time_dict, sim_dict, best_seq_ind):
        """
        This function define sequence with smallest time duration and most similar by events name
        Parameters
        -----------
        med_time_dict: (dict) - median time duration of sequences
        sim_dict: (dict) - similarity measure between all sequences and choisen sequence
        Returns 
        -----------
        (str) - sequences with best score
        """
        sim_score = {k:n for n, k in enumerate(sim_dict.keys())}
        time_score = {k:n for n, k in enumerate(med_time_dict.keys())}
        count_score = {k:n for n, k in enumerate(self.sequences_counts_ratio.keys())}
        total_score = {k: sim_score.get(k, 999) + time_score.get(k, 999) + count_score.get(k, 999) for k in sim_score.keys()}
        sortd = self.sort_dict_by_value(total_score, False)
        if len(sortd) != 0:
            assert best_seq_ind <= (len(sortd)-1), f"Max index of sequence is {len(sortd)-1}"
            return list(sortd)[best_seq_ind]
        return ""
    
    def __get_stat_time_by_transaction(self, best_seq):
        """
        This function define time diff (median) between transition of best_sequence and sequences from all log
        Parameters
        -----------
        best_seq: (str) - sequences with best score
        Returns 
        -----------
        (dict) - how different time duration for each transition of best sequence from sequences of all log
        """    
        med_time_all_log = self.__get_transact_medtime(self.base_df)
        med_time_for_seq = self.__get_transact_medtime(self.__get_df_by_id(best_seq))
        if (len(med_time_all_log) == 0) | (len(med_time_for_seq) == 0):
            print("Не найдено последовательностей с заданными конечным и начальным событием\nВозможные варианты:")
            self.get_start_end_seq_in_log()
            return {}
        return self.get_time_diff_between_events(med_time_all_log, med_time_for_seq)
    
    
    def get_faster_similar_sequence(self, choisen_seq, best_seq_ind=0):
        for_compare = self.join_events(choisen_seq)
        self.__get_seq_similarity(for_compare)
        
        med_time = self.__check_concurrency_start_end_events(for_compare, self.__get_sequences_medtime(), False)
        sim = self.__check_concurrency_start_end_events(for_compare, self.sequences_similarity, True)
        
        self.__get_seq_counts_ratio()
        best_seq = self.__select_best_sequence(med_time, sim, best_seq_ind)
        time_stat = self.__get_stat_time_by_transaction(best_seq)
        
        return best_seq, time_stat