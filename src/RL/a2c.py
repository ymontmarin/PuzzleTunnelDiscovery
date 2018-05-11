from __future__ import print_function
import tensorflow as tf
import rlenv
import numpy as np
from collections import deque
import itertools
# imsave for Debug
from scipy.misc import imsave

class A2CTrainer:
    a2c_tmax = None
    optimizer = None
    loss = None
    verbose_training = False

    def __init__(self,
            advcore,
            tmax,
            gamma,
            learning_rate,
            ckpt_dir,
            global_step=None,
            entropy_beta=0.01,
            debug=True,
            batch_normalization=None,
            period=1
            ):
        self.advcore = advcore
        self.a2c_tmax = tmax
        self.gamma = gamma
        self.entropy_beta = entropy_beta
        self.debug = debug
        self.action_space_dimension = int(advcore.policy.shape[-1])
        self.batch_normalization = batch_normalization
        '''
        Create the optimizers to train the AdvCore
        '''
        self.optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
        if period > 1:
            self.optimizer = tf.train.SyncReplicasOptimizer(self.optimizer, replicas_to_aggregate=period)
        LAMBDA = 0.5
        self.loss = LAMBDA * self.build_loss(advcore)
        print("self.loss 1 {}".format(self.loss))
        tf.summary.scalar('a2c_loss', self.loss)
        self.loss += advcore.build_loss()
        print("self.loss 2 {}".format(self.loss))
        '''
        Approach 1: Do not train Vision since we don't have reliable GT from RL procedure
        self.train_op = self.optimizer.minimize(self.loss,
                global_step=global_step,
                var_list=advcore.policy_params + advcore.value_params + advcore.lstm_params)
        '''
        '''
        Approach 2: Train everything
        '''
        if batch_normalization is not None:
            update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
            with tf.control_dependencies(update_ops):
                self.train_op = self.optimizer.minimize(self.loss, global_step=global_step)
        else:
            self.train_op = self.optimizer.minimize(self.loss, global_step=global_step)
        if ckpt_dir is not None:
            self.summary_op = tf.summary.merge_all()
            self.train_writer = tf.summary.FileWriter(ckpt_dir + '/summary', tf.get_default_graph())
        self.global_step = global_step
        self.dbg_sample_peek = 0

    def print(self, *args, **kwargs):
        if self.debug:
            print(*args, **kwargs)

    '''
    Private: Return A2C Loss

    Side effect: self.rl_params were set
    '''
    def build_loss(self, advcore):
        if self.loss is not None:
            return self.loss

        '''
        Input tensor of Ground Truth from Environment
        '''
        '''
        self.Adist_tensor = tf.placeholder(tf.float32,
                shape=[None, 1, self.action_space_dimension],
                name='ADistPh')
        '''
        self.Adist_tensor = advcore.action_tensor

        self.TD_tensor = tf.placeholder(tf.float32, shape=[None], name='TDPh')
        self.V_tensor = tf.placeholder(tf.float32, shape=[None], name='VPh')
        # self.TD_tensor = tf.placeholder(tf.float32, shape=[None])
        # self.V_tensor = tf.placeholder(tf.float32, shape=[None])

        policy = advcore.softmax_policy
        log_policy = tf.log(tf.clip_by_value(policy, 1e-20, 1.0))
        # cond_prob = tf.reduce_sum(policy * self.Adist_tensor, axis=1)
        rindices = [i for i in range(1, len(log_policy.shape))]
        self.print('rindices {}'.format(rindices))
        action_entropy = tf.reduce_sum(tf.multiply(log_policy, self.Adist_tensor),
                reduction_indices=rindices)
        entropy = -tf.reduce_sum(policy * log_policy, reduction_indices=rindices)
        self.print('action_entropy shape {}'.format(action_entropy.shape))

        # Why do we add entropy to our loss?
        # policy_loss_per_step = tf.reduce_sum(action_entropy * self.TD_tensor) + entropy * self.entropy_beta
        policy_loss_per_step = tf.reduce_sum(action_entropy * self.TD_tensor)
        policy_loss = -tf.reduce_sum(policy_loss_per_step)
        flattened_value = tf.reshape(advcore.value, [-1])
        value_loss = tf.nn.l2_loss(self.V_tensor - flattened_value)
        self.print("V_tensor {} AdvCore.value {}".format(self.V_tensor.shape, flattened_value.shape))
        self.loss = policy_loss+value_loss
        '''
        Debug: minimize w.r.t. value loss
        '''
        # self.loss = value_loss
        return self.loss

    '''
    Train the network

    This method interacts with RLEnv object to collect truths
    '''
    def train(self, envir, sess, tid=None, tmax=-1):
        if tmax < 0:
            tmax = self.a2c_tmax
        if tid is None:
            pprefix = ""
        else:
            pprefix = "[{}] ".format(tid)
        advcore = self.advcore
        reaching_terminal = False
        states = []
        actions = []
        actual_rewards = []
        combined_rewards = []
        values = []
        lstm_begin = advcore.get_lstm()
        for i in range(tmax):
            policy, value = advcore.evaluate([envir.vstate], sess, [advcore.softmax_policy, advcore.value])
            '''
            Pick up the only frame
            '''
            self.print('{}pol {} shape {}; val {} shape {}'.format(pprefix, policy, policy.shape, value, value.shape))
            policy = policy[0][0] # Policy View from first qstate and first view
            value = np.asscalar(value) # value[0][0][0]
            lstm_next = advcore.get_lstm()
            action = advcore.make_decision(envir, policy, pprefix)
            states.append(envir.vstate)
            '''
            FIXME: Wait, shouldn't be policy?
            '''
            actions.append(action)
            values.append(value)

            self.print("{}Peeking action".format(pprefix))
            nstate,reward,reaching_terminal,ratio = envir.peek_act(action, pprefix=pprefix)
            actual_rewards.append(reward)
            # print("action peeked {} ratio {} terminal? {}".format(nstate, ratio, reaching_terminal))
            reward += advcore.get_artificial_reward(envir, sess,
                    envir.qstate, action, nstate, ratio, pprefix)
            combined_rewards.append(reward)
            '''
            Store Exprience
            '''
            envir.store_erep(actions[-1], states[-1], actual_rewards[-1],
                             reaching_terminal)
            '''
            Experience Replay
            '''
            self.a2c_erep(envir, sess, pprefix)
            if reaching_terminal:
                break
            '''
            Leave for training because of collision
            '''
            if ratio == 0:
                break
            advcore.set_lstm(lstm_next) # AdvCore next frame
            envir.qstate = nstate # Envir Next frame
        advcore.set_lstm(lstm_begin)
        # self.a2c(envir, sess, actions, states, combined_rewards, values, reaching_terminal, pprefix)
        # print("> states length {}, shape {}".format(len(states), states[0][0].shape))
        # print("> actions length {}, tmax {}".format(len(actions), tmax))
        states.append(envir.vstate)
        self.train_by_samples(envir, sess, actions, states, actual_rewards,
                reaching_terminal, pprefix)
        advcore.set_lstm(lstm_next)

        if reaching_terminal:
            '''
            Train the experience in sample_cap iterations
            '''
            for i in range(envir.erep_sample_cap):
                self.a2c_erep(envir, sess, pprefix)
            envir.reset()
            assert len(envir.erep_actions) == 0, "Exp Rep is not cleared after reaching terminal"

    '''
    Private function that performs the training
    '''
    def a2c(self, envir, sess, actions, vstates, rewards, values, reaching_terminal, pprefix=""):
        advcore = self.advcore
        V = 0.0
        if not reaching_terminal:
            V = np.asscalar(advcore.evaluate([envir.vstate], sess, tensors=[advcore.value])[0])
            self.print('> V from advcore.evaluate {}'.format(V))

        # actions.reverse()
        # rewards.reverse()
        # values.reverse()
        r_actions = actions[::-1]
        r_rewards = rewards[::-1]
        r_values = values[::-1]

        batch_adist = []
        batch_td = []
        batch_V = []
        '''
        Calculate the per-step "true" value for current iteration
        '''
        '''
        print('[{}] R start with {}'.format(self.worker_thread_index, R))
        '''
        for (ai, ri, Vi) in zip(r_actions, r_rewards, r_values):
            V = ri + self.gamma * V
            td = V - Vi
            self.print("{}V(env+ar) {} V(nn) {}".format(pprefix, V, Vi))
            adist = np.zeros(shape=(1, self.action_space_dimension),
                    dtype=np.float32)
            adist[0, ai] = 1.0

            batch_adist.append(adist)
            batch_td.append(td)
            batch_V.append(V)
        batch_rgb = [state[0] for state in vstates]
        batch_dep = [state[1] for state in vstates]
        if self.verbose_training:
            self.print('{}batch_a[0] {}'.format(pprefix, batch_adist[0]))
            self.print('{}batch_V {}'.format(pprefix, batch_R))
        '''
        Always reverse, the RLEnv need this sequential info for training.
        '''
        batch_adist.reverse()
        batch_td.reverse()
        batch_V.reverse()
        dic = {
                advcore.rgb_1: batch_rgb[:-1],
                advcore.dep_1: batch_dep[:-1],
                advcore.rgb_2: batch_rgb[1:],
                advcore.dep_2: batch_dep[1:],
                advcore.action_tensor : batch_adist,
                self.TD_tensor: batch_td,
                self.V_tensor: batch_V
              }
        if self.batch_normalization is not None:
            dic[self.batch_normalization] = True
        if advcore.using_lstm:
            dic.update({
                advcore.lstm_states_in.c : advcore.current_lstm.c,
                advcore.lstm_states_in.h : advcore.current_lstm.h,
                advcore.lstm_len : len(batch_rgb[:-1])
                       })
        self.print('{}batch_td {}'.format(pprefix, batch_td))
        self.print('{}batch_V {}'.format(pprefix, batch_V))
        sess.run(self.train_op, feed_dict=dic)
        # advcore.train(sess, batch_rgb, batch_dep, batch_adist)
        # FIXME: Re-enable summary after joint the two losses.
        '''
        summary = sess.run(self.summary_op)
        self.train_writer.add_summary(summary, self.global_step)
        '''
        return batch_V

    def train_by_samples(self, envir, sess, actions, states, trewards, reaching_terminal, pprefix):
        advcore = self.advcore
        trimmed_states = states[:-1]
        if len(trimmed_states) <= 0:
            return
        arewards = advcore.get_artificial_from_experience(sess, states, actions)
        [values] = advcore.evaluate(trimmed_states, sess, [advcore.value])
        self.print(pprefix, '> ARewards {}'.format(arewards))
        # print(pprefix, '> Values {}'.format(values))
        arewards = np.reshape(arewards, newshape=(-1)).tolist()
        values = np.reshape(values, newshape=(-1)).tolist()
        self.print(pprefix, '> Values list {}'.format(values))
        rewards = []
        for (tr,ar) in zip(trewards, arewards):
            rewards.append(tr+ar)
        self.print(pprefix, '> Rewards {}'.format(rewards))
        bv = self.a2c(envir, sess, actions, states, rewards, values, reaching_terminal, pprefix)
        [valuesafter] = advcore.evaluate(trimmed_states, sess, [advcore.value])
        valuesafter = np.reshape(valuesafter, newshape=(-1)).tolist()
        self.print(pprefix, '> [DEBUG] Values before training {}'.format(values))
        self.print(pprefix, '> [DEBUG] Values target {}'.format(bv))
        self.print(pprefix, '> [DEBUG] Values after training {}'.format(valuesafter))

    '''
    a2c_erep: A2C Training with Expreience REPlay
    '''
    def a2c_erep(self, envir, sess, pprefix):
        actions, states, trewards, reaching_terminal = envir.sample_in_erep(pprefix)
        if len(actions) == 0:
            return
        self.train_by_samples(envir, sess, actions, states, trewards,
                reaching_terminal, pprefix)
