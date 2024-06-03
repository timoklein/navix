# Copyright 2023 The Navix Authors.

# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.


from __future__ import annotations
import jax

import jax.numpy as jnp
from jax import Array

from navix.entities import Wall
from navix.spaces import Space

from .rendering.cache import TILE_SIZE, unflatten_patches
from .components import DISCARD_PILE_IDX, HasColour, Openable
from .states import State
from .grid import align, idx_from_coordinates, crop, view_cone


RADIUS = 3


def none(state: State) -> Array:
    return jnp.asarray(())


def categorical(state: State) -> Array:
    # get idx of entity on the set of patches
    indices = idx_from_coordinates(state.grid, state.get_positions())
    # get tags corresponding to the entities
    tags = state.get_tags()
    # set tags on the flat set of patches
    shape = state.grid.shape
    grid = state.grid.reshape(-1).at[indices].set(tags)
    # unflatten patches to reconstruct the grid
    return grid.reshape(shape)


def categorical_first_person(state: State) -> Array:
    # get transparency map
    transparency_map = jnp.where(state.grid == 0, 1, 0)
    positions = state.get_positions()
    transparent = state.get_transparency()
    transparency_map = transparency_map.at[tuple(positions.T)].set(~transparent)

    # apply view mask
    player = state.get_player()
    view = view_cone(transparency_map, player.position, RADIUS)

    # get categorical representation
    tags = state.get_tags()
    obs = state.grid.at[tuple(positions.T)].set(tags) * view

    # crop grid to agent's view
    obs = crop(obs, player.position, player.direction, RADIUS)

    return obs


def symbolic(state: State) -> Array:
    """Fully observable grid with a symbolic state representation.
    The symbol is a triple of (OBJECT_TAG, COLOUR_IDX, OPEN/CLOSED/LOCKED), \
    where X and Y are the coordinates on the grid, and IDX is the id of the object."""
    # initialise empty observation
    minus_ones = jnp.zeros(state.grid.shape) - 1
    obs = jnp.stack([state.grid, minus_ones, minus_ones], axis=-1)

    # place entities
    for entity_class in state.entities:
        entity = state.entities[entity_class]
        tag = entity.tag
        colour = (
            entity.colour
            if isinstance(entity, HasColour)
            else jnp.zeros(entity.shape) - 1
        )
        entity_state = (
            entity.open + (entity.requires != jnp.zeros(entity.shape) - 1)
            if isinstance(entity, Openable)
            else jnp.zeros(entity.shape) - 1
        )
        entity_symbol = jnp.stack([tag, colour, entity_state], axis=-1)
        obs = obs.at[tuple(entity.position.T)].set(entity_symbol)
    return obs


def symbolic_first_person(state: State) -> Array:
    """First person view with a symbolic state representation.
    The symbol is a triple of (OBJECT_TAG, COLOUR_IDX, OPEN/CLOSED/LOCKED), \
    where X and Y are the coordinates on the grid, and IDX is the id of the object."""
    # get transparency map
    obs = symbolic(state)

    player = state.get_player()
    obs = crop(obs, player.position, player.direction, RADIUS)
    return obs


def rgb(state: State) -> Array:
    # get idx of entity on the flat set of patches
    indices = idx_from_coordinates(state.grid, state.get_positions())
    # get tiles corresponding to the entities
    tiles = state.get_sprites()
    # set tiles on the flat set of patches
    patches = state.cache.patches.at[indices].set(tiles)
    # remove discard pile
    patches = patches[:DISCARD_PILE_IDX]
    # unflatten patches to reconstruct the image
    image_size = (
        state.grid.shape[0] * TILE_SIZE,
        state.grid.shape[1] * TILE_SIZE,
    )
    image = unflatten_patches(patches, image_size)
    return image


def rgb_first_person(state: State) -> Array:
    # calculate final image size
    # get agent's view
    # image_size = (
    #     state.grid.shape[0] * TILE_SIZE,
    #     state.grid.shape[1] * TILE_SIZE,
    # )
    # transparency_map = jnp.where(state.grid == 0, 1, 0)
    # positions = state.get_positions()
    # transparent = state.get_transparency()
    # transparency_map = transparency_map.at[tuple(positions.T)].set(~transparent)
    # view = view_cone(transparency_map, player.position, RADIUS)
    # view = jax.image.resize(view, image_size, method="nearest")
    # view = jnp.tile(view[..., None], (1, 1, 3))

    # get sprites aligned to player's direction
    sprites = state.get_sprites()
    sprites = jax.vmap(lambda x: align(x, jnp.asarray(0), player.direction))(sprites)

    # align sprites to player's direction
    indices = idx_from_coordinates(state.grid, state.get_positions())
    patches = state.cache.patches.at[indices].set(sprites)

    # remove discard pile
    patches = patches[:DISCARD_PILE_IDX]
    # rearrange the sprites in a grid
    patchwork = patches.reshape(*state.grid.shape, *patches.shape[1:])

    # crop grid to agent's view
    player = state.get_player()
    patchwork = crop(patchwork, player.position, player.direction, RADIUS)

    # reconstruct image
    obs = jnp.swapaxes(patchwork, 1, 2)
    shape = obs.shape
    obs = obs.reshape(shape[0] * shape[1], shape[2] * shape[3], *shape[4:])
    return obs
