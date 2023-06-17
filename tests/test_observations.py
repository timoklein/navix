import jax
import navix as nx


def test_rgb():
    env = nx.environments.KeyDoor(10, 5, 100, observation_fn=nx.observations.rgb)
    key = jax.random.PRNGKey(4)
    state = jax.jit(env.reset)(key)
    print(state.observation)


if __name__ == "__main__":
    test_rgb()